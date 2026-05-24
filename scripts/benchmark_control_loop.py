import argparse
import sys
import time
import numpy as np

def run_benchmark(frequency: int, duration_sec: int):
    period = 1.0 / frequency
    print(f"Starting Control Loop Benchmark at {frequency}Hz (period: {period*1000:.2f}ms) for {duration_sec}s...")
    
    # Pre-allocate array for delta times
    num_ticks = int(frequency * duration_sec)
    deltas = np.zeros(num_ticks)
    
    start_time = time.monotonic()
    next_tick = start_time + period
    
    for i in range(num_ticks):
        # Precise sleep until next tick
        now = time.monotonic()
        sleep_time = next_tick - now
        if sleep_time > 0:
            time.sleep(sleep_time)
            
        wake_time = time.monotonic()
        
        # Calculate actual interval
        if i == 0:
            deltas[i] = period
        else:
            deltas[i] = wake_time - prev_wake
            
        prev_wake = wake_time
        next_tick += period
        
    actual_duration = time.monotonic() - start_time
    print("Benchmark completed. Analyzing results...")
    
    # Calculate stats (convert to milliseconds)
    deltas_ms = deltas * 1000.0
    target_period_ms = period * 1000.0
    
    mean_ms = np.mean(deltas_ms)
    std_ms = np.std(deltas_ms)
    max_ms = np.max(deltas_ms)
    min_ms = np.min(deltas_ms)
    
    # Jitter is the absolute difference from target period
    jitters_ms = np.abs(deltas_ms - target_period_ms)
    max_jitter_ms = np.max(jitters_ms)
    mean_jitter_ms = np.mean(jitters_ms)
    
    # Overruns: ticks that exceeded target period by more than 10%
    overruns = np.sum(deltas_ms > target_period_ms * 1.10)
    
    print("\n" + "="*40)
    print("           CONTROL LOOP BENCHMARK REPORT      ")
    print("="*40)
    print(f"Target Frequency:       {frequency} Hz")
    print(f"Target Period:          {target_period_ms:.3f} ms")
    print(f"Total Ticks Measured:   {num_ticks}")
    print(f"Actual Loop Duration:   {actual_duration:.3f} s")
    print("-"*40)
    print(f"Mean Cycle Time:        {mean_ms:.3f} ms")
    print(f"Min Cycle Time:         {min_ms:.3f} ms")
    print(f"Max Cycle Time:         {max_ms:.3f} ms")
    print(f"Std Deviation:          {std_ms:.3f} ms")
    print("-"*40)
    print(f"Mean Jitter:            {mean_jitter_ms:.3f} ms")
    print(f"Max Jitter:             {max_jitter_ms:.3f} ms")
    print(f"Loop Overruns (>10%):   {overruns} ({overruns/num_ticks*100.0:.2f}%)")
    print("="*40)
    
    if overruns == 0 and max_jitter_ms < 1.5:
        print("RESULT: PASS (Real-Time loop is stable and deterministic)")
    else:
        print("RESULT: WARNING (Timing jitter or overruns detected. Enable PREEMPT_RT or adjust pinning.)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Control Loop Jitter and Overrun Profiler.")
    parser.add_argument("--frequency", type=int, default=50, help="Target frequency in Hz (default: 50)")
    parser.add_argument("--duration", type=int, default=10, help="Benchmark duration in seconds (default: 10)")
    args = parser.parse_args()
    
    run_benchmark(args.frequency, args.duration)
