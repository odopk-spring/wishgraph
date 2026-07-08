# PaperChat Validation Loop

The stable execution loop was:

```text
read task spec
-> inspect anchored files
-> implement minimal patch
-> run build/tests/previews or manual checks
-> update CODEMAP
-> update task status
-> produce Dev Report
-> create one atomic commit when requested
```

## Why This Matters

The loop gave each agent a durable exit condition. "Done" did not mean "I changed code." It meant:

- The requested behavior changed.
- The validation surface ran or the gap was recorded.
- The project map stayed current.
- The next agent could continue without chat history.
