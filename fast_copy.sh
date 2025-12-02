#!/bin/bash

# =========================================
# Fast Copy Script with Threading & Cancel
# =========================================

# Source and destination directories
SRC_DIR="$1"
DEST_DIR="$2"

# Default number of threads
THREADS=1

# Optional threads argument
if [[ "$3" == "--thread" ]] && [[ -n "$4" ]]; then
    THREADS="$4"
fi

# Validate input arguments
if [ -z "$SRC_DIR" ] || [ -z "$DEST_DIR" ]; then
    echo "Usage: $0 /path/to/source /path/to/destination [--thread N]"
    exit 1
fi

# =========================================
# Temporary files
# =========================================
FILE_LIST=$(mktemp)
COUNTER_FILE=$(mktemp)
echo 0 > "$COUNTER_FILE"

# =========================================
# Cleanup function for graceful cancellation
# =========================================
cleanup() {
    rm -f "$FILE_LIST" "$COUNTER_FILE"
    echo "Copy canceled!"
    exit 1
}
# Catch Ctrl+C or SIGTERM
trap cleanup SIGINT SIGTERM

echo "Starting copy from '$SRC_DIR' → '$DEST_DIR' (threads: $THREADS)"

# =========================================
# Pre-scan for files that actually need copying
# =========================================
while IFS= read -r -d '' FILE; do
    REL_PATH="${FILE#$SRC_DIR/}"
    DEST_FILE="$DEST_DIR/$REL_PATH"

    # Skip if the destination exists and sizes match
    if [ -f "$DEST_FILE" ]; then
        SRC_SIZE=$(stat -f%z "$FILE")
        DST_SIZE=$(stat -f%z "$DEST_FILE")
        [ "$SRC_SIZE" -eq "$DST_SIZE" ] && continue
    fi

    # Append file to the list of files to copy
    echo "$FILE" >> "$FILE_LIST"
done < <(find "$SRC_DIR" -type f ! -name ".DS_Store" -print0)

# =========================================
# Determine total files and padding width
# =========================================
TOTAL_FILES=$(wc -l < "$FILE_LIST" | tr -d ' ')
PAD_WIDTH=${#TOTAL_FILES}

# =========================================
# Thread-safe counter function
# =========================================
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

# =========================================
# Function to copy a single file
# =========================================
copy_file() {
    FILE="$1"
    REL_PATH="${FILE#$SRC_DIR/}"
    DEST_FILE="$DEST_DIR/$REL_PATH"

    # Ensure destination directory exists
    mkdir -p "$(dirname "$DEST_FILE")"

    # Increment counter safely and print progress
    CURRENT=$(increment_counter "$COUNTER_FILE")
    printf "(%0*d/%0*d) Copying: '%s'\n" "$PAD_WIDTH" "$CURRENT" "$PAD_WIDTH" "$TOTAL_FILES" "$REL_PATH"

    # Perform the actual copy while preserving metadata
    tar cf - -C "$(dirname "$FILE")" "$(basename "$FILE")" | tar xf - -C "$(dirname "$DEST_FILE")"
}

# =========================================
# Export functions and variables for xargs
# =========================================
export -f copy_file increment_counter
export SRC_DIR DEST_DIR TOTAL_FILES COUNTER_FILE PAD_WIDTH

# =========================================
# Perform the copy with optional threading
# =========================================
if [ "$THREADS" -gt 1 ]; then
    # Use xargs with null-delimited input for multi-threading
    tr '\n' '\0' < "$FILE_LIST" | xargs -0 -n1 -P"$THREADS" bash -c 'copy_file "$0"' 
else
    # Single-threaded fallback
    while IFS= read -r FILE; do
        copy_file "$FILE"
    done < "$FILE_LIST"
fi

# =========================================
# Cleanup temporary files and finish
# =========================================
rm -f "$FILE_LIST" "$COUNTER_FILE"
echo "Copy complete!"
