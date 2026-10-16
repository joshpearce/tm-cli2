# shellcheck shell=bash
# Library for tm-cli tmux-driven Claude demos.
#
# Source this from a demo script, then call:
#   demo_init                 # sanity-check, reset db, configure shell, launch Claude
#   ask "..."                 # one prompt at a time (repeat as needed)
#   demo_done                 # print final attach hint
#
# Anything declared here with ": ${VAR:=default}" can be overridden by the
# caller (demo script or environment) before `demo_init` runs. Anything else
# is internal.

# --- Config (override before demo_init) ------------------------------------

# Name of the tmux session to drive. Must already exist.
: "${TMUX_SESSION:=demo}"

# SQLite db file to expose as TM_DB_PATH inside the session. Deleted at
# demo_init so each run begins from an empty database.
: "${TM_DB_FILE:=$HOME/code/tm-cli/demo.db}"

# Path to the `tm` binary; its directory is prepended to PATH in the
# session so Claude's Bash subshells can resolve `tm`.
: "${TM_BIN:=$HOME/code/tm-cli/.venv/bin/tm}"

# dfd_editor server URL — Claude pushes the live diagram here at the end
# of each build phase so a connected browser can render the model.
: "${DFD_EDITOR_URL:=http://localhost:5050}"

# How long to wait for Claude's TUI to first appear (seconds).
: "${TUI_READY_TIMEOUT:=30}"

# Polling interval (seconds) used by the readiness loop.
: "${POLL_INTERVAL:=1}"

# Words-per-minute for the typing simulator. 60 ≈ average human typist.
# Bump higher (e.g. 200) if you want to skip the visual typing effect.
: "${TYPING_WPM:=200}"

# When set (any non-empty value), skip the "Press ENTER" prompt between
# asks and just auto-wait for Claude to go idle. Inherited from the
# environment so you can run e.g.  AUTO_PACE=1 bash run-demo.sh.
: "${AUTO_PACE:=}"

# Name + metadata for the pre-created "default" diagram. Demo scripts
# that target a different domain should override DIAGRAM_DESCRIPTION.
: "${DIAGRAM_NAME:=default}"
: "${DIAGRAM_AUTHOR:=tm-cli demo}"
: "${DIAGRAM_DESCRIPTION:=Threat model — built live via the tm CLI.}"

# Boolean Claude CLI flags (those that take no argument) to pass at launch.
# Override to drop --dangerously-skip-permissions, add --debug, etc.
: "${CLAUDE_FLAGS:=}"

# Behavioral rules that get appended to Claude's default system prompt for
# the demo session. Generic on purpose — no project specifics — so the
# same launch wrapper works for any tm-cli threat-modeling session.
# Avoid apostrophes; we single-quote this on the command line.
: "${SYSTEM_PROMPT:=You are operating the \`tm\` CLI in a live threat-modeling session. The user will send one short prompt at a time. Execute each prompt exactly as written: no clarifying questions, no alternative suggestions, no unsolicited commentary. After every change to the model, push the diagram so the editor view stays in sync. Work entity-first; skip \`tm document\`.}"

# --- Reusable helpers -------------------------------------------------------

# capture_pane: print the visible contents of the target pane to stdout.
capture_pane() {
    tmux capture-pane -p -t "$TMUX_SESSION"
}

# pane_has: true iff the captured pane matches the given extended regex.
pane_has() {
    capture_pane | grep -qE "$1"
}

# pane_title: print the current pane title (set by Claude via OSC 2).
pane_title() {
    tmux display-message -p -t "$TMUX_SESSION" '#{pane_title}'
}

# Claude updates the pane title to "<glyph> <session-summary>" via OSC 2.
# The summary is "Claude Code" before the first prompt and a topic-derived
# string thereafter; the *leading glyph* is what signals state:
#   ✳   → idle
#   ⠀-⣿ → working (Braille spinner block, U+2800–U+28FF, glyph cycles)
# We match on the leading glyph alone so the predicates survive both the
# initial "Claude Code" suffix and any topic summary Claude picks later.

claude_idle() {
    [[ "$(pane_title)" == "✳ "* ]]
}

claude_working() {
    local first
    first=$(pane_title | cut -c1)
    # Any character in the Braille block other than ✳.
    [[ "$first" != "✳" ]] && printf '%s' "$first" | grep -qE '[⠀-⣿]'
}

claude_running() {
    claude_idle || claude_working
}

# wait_for_tui_ready: block until Claude's TUI is up. Uses pane_title
# (set via OSC 2 by Claude itself) rather than scraping visible content,
# since the input-box glyph varies by theme but the title doesn't.
wait_for_tui_ready() {
    local timeout="${1:-$TUI_READY_TIMEOUT}"
    echo -n "Waiting for Claude TUI"
    local elapsed=0
    while (( elapsed < timeout )); do
        if claude_running; then
            echo " ready."
            return 0
        fi
        sleep "$POLL_INTERVAL"
        elapsed=$(( elapsed + POLL_INTERVAL ))
        echo -n "."
    done
    echo
    echo "Timed out waiting for Claude TUI." >&2
    return 1
}

# tmux_status: print pane_title plus a one-word idle/working/down summary.
# pane_title is set by Claude via OSC 2 and is the most reliable signal.
tmux_status() {
    local title state
    title=$(pane_title)
    if claude_idle; then
        state=idle
    elif claude_working; then
        state=working
    else
        state=down
    fi
    printf '  [state=%s | pane_title=%q]\n' "$state" "$title"
}

# wait_for_claude_idle: poll pane_title until Claude transitions back to
# the idle "✳ ..." state. Sleeps briefly first so we don't race past the
# working state — Claude can take a beat to start the turn after a paste.
# Default timeout is generous; tune via the first arg if needed.
wait_for_claude_idle() {
    local timeout="${1:-300}"
    sleep 1
    local elapsed=0
    while (( elapsed < timeout )); do
        if claude_idle; then
            return 0
        fi
        sleep "$POLL_INTERVAL"
        elapsed=$(( elapsed + POLL_INTERVAL ))
    done
    return 1
}

# pause: gate progression to the next prompt. Default is interactive
# (sample state, block on ENTER) so a human can verify the demo pane
# between prompts. Set AUTO_PACE=1 (or pipe stdin from /dev/null) to
# skip the ENTER wait and auto-detect Claude going idle instead — the
# script then drives Claude end-to-end without supervision.
pause() {
    if [[ -z "$AUTO_PACE" && -t 0 ]]; then
        sleep 1.5  # let Claude transition into the working state
        tmux_status
        read -rp "  Press ENTER to continue... "
    else
        echo -n "  waiting for Claude to finish"
        local started=$SECONDS
        if wait_for_claude_idle; then
            echo " (idle in $(( SECONDS - started ))s)"
        else
            echo " (TIMED OUT)"
        fi
        tmux_status
    fi
}

# type_into_pane: send text to the pane one character at a time, with
# per-keystroke timing chosen to feel like a typist at $TYPING_WPM. Light
# jitter (70%–130% of the base interval) keeps the rhythm from looking
# robotic. Iterates Unicode code points via Python so multi-byte glyphs
# (em-dashes, arrows ↔, …) get sent intact rather than as broken bytes
# (which is what bash's ${text:i:1} would produce).
type_into_pane() {
    local text="$1"
    local target="${2:-$TMUX_SESSION}"
    local wpm="${3:-$TYPING_WPM}"
    python3 - "$text" "$target" "$wpm" <<'PY'
import sys, time, subprocess, random
text, target = sys.argv[1], sys.argv[2]
wpm = float(sys.argv[3])
# 1 word ≈ 5 chars, so chars/sec = wpm * 5 / 60 → seconds/char = 60 / (wpm * 5).
base = 60.0 / (wpm * 5.0)
for ch in text:
    subprocess.run(
        ["tmux", "send-keys", "-t", target, "-l", "--", ch],
        check=True,
    )
    time.sleep(base * random.uniform(0.7, 1.3))
PY
}

# send_prompt: type a prompt into Claude's input box (visibly, via the
# typing simulator) and submit it. Enter is sent as a separate, non-literal
# send-keys call so tmux interprets it as the Return key, not the literal
# text "Enter".
send_prompt() {
    local prompt="$1"
    type_into_pane "$prompt"
    sleep 0.3
    tmux send-keys -t "$TMUX_SESSION" Enter
}

# ask: send a prompt, then pause for manual confirmation before continuing.
ask() {
    local prompt="$1"
    echo "→ $prompt"
    send_prompt "$prompt"
    pause
}

# shell_send: type a shell command into the pane (no Claude involved).
shell_send() {
    tmux send-keys -t "$TMUX_SESSION" -l -- "$1"
    tmux send-keys -t "$TMUX_SESSION" Enter
}

# pane_shell: print the shell currently running in the pane (e.g. "fish",
# "bash", "zsh"). Used by shell_export / shell_path_prepend to pick the
# right syntax — must be called *before* Claude is launched, since once
# Claude is running pane_current_command becomes Claude's exec name.
pane_shell() {
    tmux display-message -p -t "$TMUX_SESSION" '#{pane_current_command}'
}

# shell_export: set an env var in the parent shell so Claude (and Claude's
# Bash subshells) inherits it. Aliases don't propagate to non-interactive
# subshells; env vars do.
shell_export() {
    local var="$1" val="$2"
    case "$(pane_shell)" in
        fish) shell_send "set -gx $var '$val'" ;;
        *)    shell_send "export $var='$val'" ;;
    esac
}

# shell_path_prepend: prepend a directory to PATH in the parent shell.
shell_path_prepend() {
    local dir="$1"
    case "$(pane_shell)" in
        fish) shell_send "set -gx PATH '$dir' \$PATH" ;;
        *)    shell_send "export PATH='$dir:'\"\$PATH\"" ;;
    esac
}

# --- Lifecycle -------------------------------------------------------------

# demo_init: full pre-flight — sanity-check the environment, reset the db,
# configure the pane shell, pre-create the "default" diagram, broadcast it
# to dfd_editor, then launch Claude with the appended system prompt and
# wait for the TUI to come up. After this returns, the pane is ready for
# `ask` calls.
demo_init() {
    # Sanity checks
    command -v tmux   >/dev/null || { echo "tmux not on PATH" >&2; exit 1; }
    command -v claude >/dev/null || { echo "claude CLI not on PATH" >&2; exit 1; }
    [[ -x "$TM_BIN" ]] || { echo "tm binary not executable: $TM_BIN" >&2; exit 1; }

    # Require the session to already exist.
    if ! tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        echo "tmux session not found: $TMUX_SESSION" >&2
        echo "Start it first, e.g.:  tmux new -s $TMUX_SESSION" >&2
        exit 1
    fi
    echo "Targeting tmux session: $TMUX_SESSION"

    # Reset the database so each run starts from a clean slate. tm/sqlite
    # will recreate the file on first write.
    if [[ -f "$TM_DB_FILE" ]]; then
        echo "Removing existing $TM_DB_FILE for a fresh run."
        rm -f "$TM_DB_FILE"
    fi

    # Configure the shell in the session: export TM_DB_PATH +
    # DFD_EDITOR_URL, and put the tm binary's dir on PATH. We use env /
    # PATH (not alias) because Claude's Bash tool spawns non-interactive
    # subshells that don't inherit aliases — only env. C-c first to bail
    # out of anything currently running in the pane.
    tmux send-keys -t "$TMUX_SESSION" C-c
    sleep 0.2
    echo "Detected pane shell: $(pane_shell)"
    shell_export TM_DB_PATH "$TM_DB_FILE"
    shell_export DFD_EDITOR_URL "$DFD_EDITOR_URL"
    shell_path_prepend "$(dirname "$TM_BIN")"

    # Pre-create the "default" diagram so Claude can rely on the CLI's
    # default-diagram fallback for every entity command — no
    # TM_DIAGRAM_ID fiddling, no id chatter in the prompts. Push it once
    # so dfd_editor mints a remote_id, then POST /display so any
    # connected editor tab opens it.
    echo "Pre-creating '$DIAGRAM_NAME' diagram and opening in dfd_editor..."
    TM_DB_PATH="$TM_DB_FILE" "$TM_BIN" diagram create \
        --name "$DIAGRAM_NAME" \
        --author "$DIAGRAM_AUTHOR" \
        --description "$DIAGRAM_DESCRIPTION" \
        >/dev/null
    local push_json remote_id
    push_json=$(TM_DB_PATH="$TM_DB_FILE" "$TM_BIN" diagram push --server "$DFD_EDITOR_URL")
    remote_id=$(printf '%s' "$push_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["remote_id"])')
    curl -fsS -X POST "$DFD_EDITOR_URL/api/agent/diagrams/$remote_id/display" >/dev/null
    echo "  remote_id=$remote_id (display broadcast delivered)"

    # Launch Claude in auto-accept mode with our session-behavior system
    # prompt appended, then wait for the TUI to render.
    shell_send "claude $CLAUDE_FLAGS --append-system-prompt '$SYSTEM_PROMPT'"
    wait_for_tui_ready
    echo "Claude TUI is up."

    # Send Ctrl+L into the TUI so Claude redraws against an empty pane —
    # hides the launch command and any setup chatter above it.
    sleep 0.3
    tmux send-keys -t "$TMUX_SESSION" C-l
    tmux clear-history -t "$TMUX_SESSION"

    tmux_status
}

# demo_done: print the final attach hint. Call at the end of a demo script.
demo_done() {
    echo "Demo script complete. Attach with:  tmux attach -t $TMUX_SESSION"
}
