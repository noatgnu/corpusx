#!/usr/bin/env bash
IFS=',' read -ra words <<< "$1"   # Split comma-separated words into an array
for word in "${words[@]}"; do
    grep -inoE "(^|[^[:alnum:]_-])(($word)(_|;|-)?)(\b|[^[:alnum:]_-])" "$2" | awk -v word="$word" '{print word ": " $0}'      # Search for each word case-insensitively
done