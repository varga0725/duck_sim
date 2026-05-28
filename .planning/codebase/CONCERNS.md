# Codebase Concerns

**Analysis Date:** 2026-05-28

## Tech Debt

**Missing Locomotion Alignment Report:**
- Issue: `tests/test_phase3_final_alignment.py` expects `docs/phase3_final_upstream_locomotion_alignment_report.md` to exist and contain specific phase alignment summary sections, but the file is currently missing.
- Impact: Pytest test suite fails (1 failing test).
- Fix approach: Write the locomotion alignment report with the expected sections in the `docs` directory.

## Known Bugs

**Shared Memory Initialization Failure:**
- Symptoms: Warning output `Failed to initialize shared memory block 'duck_robot_sensors': [Errno 2] No such file or directory: '/duck_robot_sensors'` occurs during test runs or when starting the application in certain environments.
- Root cause: The shared memory block is expected to be created/running by another process when DUCK_MULTIPROCESS is true or when tests attempt IPC routing without pre-initialization.

**SharedMemory Destructor Buffer Error:**
- Symptoms: `BufferError: cannot close exported pointers exist` raised by `SharedMemory.__del__` inside Python's multiprocessing cleanup.
- Root cause: Shared memory handles are deleted/closed before underlying buffers or exported pointer views are fully cleared.

## Fragile Areas

**Shared Memory IPC Blocks (`duck_robot_sensors`):**
- Why fragile: Hard dependency on specific Unix/macOS shared memory allocations. If the process is terminated uncleanly, the shared memory segment might leak or block subsequent initializations.
- Test coverage: Tested in `tests/test_vision_ipc.py`.

---

*Concerns audit: 2026-05-28*
*Update as issues are fixed or new ones discovered*
