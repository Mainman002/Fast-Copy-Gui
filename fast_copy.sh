#!/bin/bash

# =========================================
# Fast Copy Script (Cross-Platform: macOS + Linux)
# =========================================

SRC_DIR="$1"
DEST_DIR="$2"

THREADS=1
if [[ "$3" == "--thread" && -n "$4" ]]; then
    THREADS="$4"
fi

if [ -z "$SRC_DIR" ] || [ -z "$DEST_DIR" ]; then
    echo "Usage: $0 /path/to/source /path/to/destination [--thread N]"
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

echo "Starting copy from '$SRC_DIR' → '$DEST_DIR' (threads: $THREADS)"

# =========================================
# Build file list (null-delimited)
# =========================================
while IFS= read -r -d '' FILE; do
    REL_PATH="${FILE#$SRC_DIR/}"
    DEST_FILE="$DEST_DIR/$REL_PATH"

    if [ -f "$DEST_FILE" ]; then
        SRC_SIZE=$($STAT_SIZE "$FILE")
        DST_SIZE=$($STAT_SIZE "$DEST_FILE")
        [ "$SRC_SIZE" -eq "$DST_SIZE" ] && continue
    fi

    printf "%s\0" "$FILE" >> "$FILE_LIST"
done < <(find "$SRC_DIR" -type f -print0)

# =========================================
# Count files
# =========================================
TOTAL_FILES=$(tr -cd '\0' < "$FILE_LIST" | wc -c)
PAD_WIDTH=${#TOTAL_FILES}

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
    REL_PATH="${FILE#$SRC_DIR/}"
    DEST_FILE="$DEST_DIR/$REL_PATH"

    mkdir -p "$(dirname "$DEST_FILE")"

    CURRENT=$(increment_counter "$COUNTER_FILE")
    printf "(%0*d/%0*d) Copying: '%s'\n" \
        "$PAD_WIDTH" "$CURRENT" "$PAD_WIDTH" "$TOTAL_FILES" "$REL_PATH"

    # Portable tar copy (works on GNU + BSD)
    tar cf - -C "$(dirname "$FILE")" "$(basename "$FILE")" \
        | tar xf - -C "$(dirname "$DEST_FILE")"
}

export -f copy_file increment_counter
export SRC_DIR DEST_DIR TOTAL_FILES COUNTER_FILE PAD_WIDTH STAT_SIZE

# =========================================
# Copy with threading (xargs)
# =========================================
if [ "$THREADS" -gt 1 ]; then
    xargs -0 -I{} -P"$THREADS" bash -c 'copy_file "$1"' _ "{}" < "$FILE_LIST"
    # xargs -0 -n1 -P"$THREADS" bash -c 'copy_file "$0"' < "$FILE_LIST"
else
    while IFS= read -r -d '' FILE; do
        copy_file "$FILE"
    done < "$FILE_LIST"
fi

rm -f "$FILE_LIST" "$COUNTER_FILE"
echo "Copy complete!"
