#!/bin/bash

# =========================================
# Fast Copy Script (Cross-Platform: macOS + Linux)
# =========================================

SRC_DIR="$1"
DEST_DIR="$2"

THREADS=1
MOVE_MODE=0

# Parse flags
shift 2
while [[ $# -gt 0 ]]; do
    case "$1" in
        --thread)
            THREADS="$2"
            shift 2
            ;;
        --move)
            MOVE_MODE=1
            shift
            ;;
        *)
            shift
            ;;
    esac
done

if [ -z "$SRC_DIR" ] || [ -z "$DEST_DIR" ]; then
    echo "Usage: fast_copy.sh /source /dest [--thread N] [--move]"
    exit 1
fi

# =========================================
# Platform detection for BSD vs GNU stat
# =========================================
if stat --version >/dev/null 2>&1; then
    # GNU stat (Linux)
    STAT_SIZE="stat -c%s"
else
    # BSD stat (macOS)
    STAT_SIZE="stat -f%z"
fi

# =========================================
# Temp files (POSIX-safe mktemp)
# =========================================
FILE_LIST=$(mktemp "${TMPDIR:-/tmp}"/fastcopy_files.XXXXXX)
COUNTER_FILE=$(mktemp "${TMPDIR:-/tmp}"/fastcopy_count.XXXXXX)
echo 0 > "$COUNTER_FILE"

cleanup() {
    rm -f "$FILE_LIST" "$COUNTER_FILE"
    echo "Copy canceled!"
    exit 1
}
trap cleanup SIGINT SIGTERM

echo "Starting copy from '$SRC_DIR' → '$DEST_DIR' (threads: $THREADS, move=$MOVE_MODE)"

# =========================================
# Build file list (null-delimited)
# =========================================
find "$SRC_DIR" -type f -print0 | while IFS= read -r -d '' FILE; do
    [[ "$(basename "$FILE")" == ".DS_Store" ]] && continue

    REL_PATH="${FILE#$SRC_DIR/}"
    DEST_FILE="$DEST_DIR/$REL_PATH"

    if [ -f "$DEST_FILE" ] && [ "$MOVE_MODE" -eq 0 ]; then
        SRC_SIZE=$($STAT_SIZE "$FILE")
        DST_SIZE=$($STAT_SIZE "$DEST_FILE")
        [ "$SRC_SIZE" -eq "$DST_SIZE" ] && continue
    fi

    printf '%s\0' "$FILE" >> "$FILE_LIST"
done

# =========================================
# Count files
# =========================================
TOTAL_FILES=$(tr -cd '\0' < "$FILE_LIST" | wc -c)
PAD_WIDTH=3

# PADDING_TOTAL_FILES=$(awk -v RS='\0' 'END {print NR}' "$FILE_LIST")
# PAD_WIDTH=$(( ${#PADDING_TOTAL_FILES} + 1 ))
# PAD_WIDTH=${#PADDING_TOTAL_FILES}

increment_counter() {
    LOCKDIR="$1.lock"

    while ! mkdir "$LOCKDIR" 2>/dev/null; do
        sleep 0.01
    done

    CURRENT=$(($(cat "$1") + 1))
    echo "$CURRENT" > "$1"
    rmdir "$LOCKDIR"

    echo "$CURRENT"
}

copy_file() {
    FILE="$1"
    [[ "$(basename "$FILE")" == ".DS_Store" ]] && return

    REL_PATH="${FILE#$SRC_DIR/}"
    DEST_FILE="$DEST_DIR/$REL_PATH"
    DEST_TMP="${DEST_FILE}.tmp"

    mkdir -p "$(dirname "$DEST_FILE")"

    # Disk space check
    avail=$(df -k "$DEST_DIR" | tail -1 | awk '{print $4*1024}')
    size=$($STAT_SIZE "$FILE")

    if [ "$size" -gt "$avail" ]; then
        echo "Skipping $FILE: not enough space"
        return
    fi

    if [ "$MOVE_MODE" -eq 1 ]; then
        # ===========================
        # MOVE MODE
        # ===========================
        # Atomic across different volumes
        mv "$FILE" "$DEST_TMP"
        mv -f "$DEST_TMP" "$DEST_FILE"
    else
        # ===========================
        # COPY MODE
        # ===========================
        if [ ! -f "$DEST_FILE" ] || [ $($STAT_SIZE "$FILE") -ne $($STAT_SIZE "$DEST_FILE") ]; then
            cp -v "$FILE" "$DEST_TMP"
            mv -f "$DEST_TMP" "$DEST_FILE"
        fi
    fi

    CURRENT=$(increment_counter "$COUNTER_FILE")
    printf "(%0${PAD_WIDTH}d/%0${PAD_WIDTH}d) Copying: '%s'\n" "$CURRENT" "$TOTAL_FILES" "$REL_PATH"


}

export -f copy_file increment_counter
export SRC_DIR DEST_DIR TOTAL_FILES COUNTER_FILE PAD_WIDTH STAT_SIZE MOVE_MODE

# =========================================
# Copy with threading (xargs)
# =========================================
if [ "$THREADS" -gt 1 ]; then
    xargs -0 -n1 -P"$THREADS" bash -c 'copy_file "$0"' < "$FILE_LIST"
else
    while IFS= read -r -d '' FILE; do
        copy_file "$FILE"
    done < "$FILE_LIST"
fi

rm -f "$FILE_LIST" "$COUNTER_FILE"
echo "Copy complete!"
