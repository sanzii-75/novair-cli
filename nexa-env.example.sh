#!/usr/bin/env bash
# nexa environment configuration — source this file or copy the lines you need
# into ~/.bashrc / ~/.zprofile.
#
#   cp nexa-env.example.sh ~/.nexa-env && echo 'source ~/.nexa-env' >> ~/.bashrc

# ── OpenRouter (featured preset) ─────────────────────────────────────────────
# One key, hundreds of models: https://openrouter.ai/keys
export NEXA_OPENROUTER_API_KEY="sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
# Optional default model for the openrouter profile:
# export NEXA_OPENROUTER_MODEL="anthropic/claude-3.5-sonnet"

# Or use the well-known OpenAI names (also recognized by nexa):
# export OPENROUTER_API_KEY="sk-or-v1-..."

# ── Default / generic OpenAI-compatible profile ─────────────────────────────
# Used when no --provider is given and no OpenRouter key is set.
# export NEXA_API_KEY="sk-..."
# export NEXA_BASE_URL="https://api.openai.com/v1"     # any OpenAI-compatible endpoint
# export NEXA_MODEL="gpt-4o-mini"

# ── Custom profiles (multi-provider, still env-only) ────────────────────────
# Pattern: NEXA_PROFILE_<NAME>_API_KEY / _BASE_URL / _MODEL
# Then run:  nexa --provider groq chat
# export NEXA_PROFILE_GROQ_API_KEY="gsk_..."
# export NEXA_PROFILE_GROQ_BASE_URL="https://api.groq.com/openai/v1"
# export NEXA_PROFILE_GROQ_MODEL="llama-3.3-70b-versatile"
#
# export NEXA_PROFILE_LOCAL_BASE_URL="http://localhost:11434/v1"   # Ollama
# export NEXA_PROFILE_LOCAL_MODEL="llama3.1"

# Pick a default provider without typing --provider every time (optional):
# export NEXA_PROVIDER="openrouter"
