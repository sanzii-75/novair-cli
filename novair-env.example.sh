#!/usr/bin/env bash
# novair environment configuration — source this file or copy the lines you need
# into ~/.bashrc / ~/.zprofile.
#
#   cp novair-env.example.sh ~/.novair-env && echo 'source ~/.novair-env' >> ~/.bashrc

# ── OpenRouter (featured preset) ─────────────────────────────────────────────
# One key, hundreds of models: https://openrouter.ai/keys
export NOVAIR_OPENROUTER_API_KEY="sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
# Optional default model for the openrouter profile:
# export NOVAIR_OPENROUTER_MODEL="anthropic/claude-3.5-sonnet"

# Or use the well-known OpenAI names (also recognized by novair):
# export OPENROUTER_API_KEY="sk-or-v1-..."

# ── Default / generic OpenAI-compatible profile ─────────────────────────────
# Used when no --provider is given and no OpenRouter key is set.
# export NOVAIR_API_KEY="sk-..."
# export NOVAIR_BASE_URL="https://api.openai.com/v1"     # any OpenAI-compatible endpoint
# export NOVAIR_MODEL="gpt-4o-mini"

# ── Custom profiles (multi-provider, still env-only) ────────────────────────
# Pattern: NOVAIR_PROFILE_<NAME>_API_KEY / _BASE_URL / _MODEL
# Then run:  novair --provider groq chat
# export NOVAIR_PROFILE_GROQ_API_KEY="gsk_..."
# export NOVAIR_PROFILE_GROQ_BASE_URL="https://api.groq.com/openai/v1"
# export NOVAIR_PROFILE_GROQ_MODEL="llama-3.3-70b-versatile"
#
# export NOVAIR_PROFILE_LOCAL_BASE_URL="http://localhost:11434/v1"   # Ollama
# export NOVAIR_PROFILE_LOCAL_MODEL="llama3.1"

# Pick a default provider without typing --provider every time (optional):
# export NOVAIR_PROVIDER="openrouter"
