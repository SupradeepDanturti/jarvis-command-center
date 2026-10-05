# Native Windows GNU Make; every recipe uses the existing PowerShell workflow.
SHELL := cmd.exe
.DEFAULT_GOAL := help
.NOTPARALLEL:

PYTHON ?= python
PORT ?= 18761
JARVIS ?= 1
ASSISTANT ?= 1

TARGETS := help install install-dev install-voice https run run-local startup start stop restart remove-startup test check
.PHONY: $(TARGETS)

$(TARGETS):
	powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/make.ps1 -Target $@ -Python "$(PYTHON)" -Port $(PORT) -Jarvis $(JARVIS) -Assistant $(ASSISTANT)
