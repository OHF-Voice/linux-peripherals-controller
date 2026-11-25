# Behavior Guide

This page describes what Linux Peripherals Controller (LPC) does, from the user's point of view. It is the source of truth for the behavior of LPC: code changes follow it, and a change of the behavior updates it.

## Startup

LPC logs its version, the address of the LVA peripheral API and then starts the peripheral drivers.

No peripheral drivers are implemented yet, so LPC only logs a warning and exits.
