// Job polling state machine (CONTRACT §10: GET /api/jobs/{id}). Pure, unit tested.
// The hook in useJob.ts drives it with a timer; nothing here touches the network.
import type { Job } from '../types';

export type PollState<R = unknown> =
  | { phase: 'idle' }
  | { phase: 'polling'; jobId: string; status: 'queued' | 'running'; log: string[]; failures: number; startedAt: number }
  | { phase: 'done'; jobId: string; result: R; log: string[]; startedAt: number; endedAt: number }
  | { phase: 'error'; jobId: string | null; error: string; log: string[]; startedAt: number; endedAt: number };

export type PollEvent<R = unknown> =
  | { type: 'start'; jobId: string; now: number }
  | { type: 'response'; job: Job<R>; now: number }
  | { type: 'network_error'; message: string; now: number }
  | { type: 'reset' };

/** Consecutive failed polls tolerated before giving up (the server may be restarting). */
export const MAX_POLL_FAILURES = 5;

export function pollReducer<R>(state: PollState<R>, ev: PollEvent<R>): PollState<R> {
  switch (ev.type) {
    case 'reset':
      return { phase: 'idle' };
    case 'start':
      return { phase: 'polling', jobId: ev.jobId, status: 'queued', log: [], failures: 0, startedAt: ev.now };
    case 'response': {
      if (state.phase !== 'polling' || ev.job.id !== state.jobId) return state; // stale answer
      const log = ev.job.log ?? state.log;
      switch (ev.job.status) {
        case 'queued':
        case 'running':
          return { ...state, status: ev.job.status, log, failures: 0 };
        case 'done':
          return { phase: 'done', jobId: state.jobId, result: ev.job.result, log, startedAt: state.startedAt, endedAt: ev.now };
        case 'error':
          return {
            phase: 'error', jobId: state.jobId, error: ev.job.error || 'The job failed without saying why.',
            log, startedAt: state.startedAt, endedAt: ev.now,
          };
        default:
          return {
            phase: 'error', jobId: state.jobId, error: `Unknown job status "${String(ev.job.status)}"`,
            log, startedAt: state.startedAt, endedAt: ev.now,
          };
      }
    }
    case 'network_error': {
      if (state.phase !== 'polling') return state;
      const failures = state.failures + 1;
      if (failures >= MAX_POLL_FAILURES) {
        return {
          phase: 'error', jobId: state.jobId,
          error: `Lost contact with the server (${ev.message}). The job may still be running.`,
          log: state.log, startedAt: state.startedAt, endedAt: ev.now,
        };
      }
      return { ...state, failures };
    }
  }
}

export function isActive(s: PollState<unknown>): boolean {
  return s.phase === 'polling';
}

/** Back off gently: 1 s while fresh, 2 s after 20 s, 4 s after a failure streak. */
export function nextDelayMs(s: PollState<unknown>, now: number): number {
  if (s.phase !== 'polling') return 0;
  if (s.failures > 0) return 1000 * Math.min(4, 2 ** s.failures);
  return now - s.startedAt > 20_000 ? 2000 : 1000;
}

/** "Building · 14 s · Exporting glTF" for the progress line. */
export function describe(s: PollState<unknown>, now: number, label = 'Working'): string {
  const secs = (end: number, start: number) => Math.max(0, Math.round((end - start) / 1000));
  switch (s.phase) {
    case 'idle':
      return '';
    case 'polling': {
      const last = s.log.length ? s.log[s.log.length - 1] : s.status === 'queued' ? 'Waiting to start' : 'Started';
      return `${label} · ${secs(now, s.startedAt)} s · ${last}`;
    }
    case 'done':
      return `Done in ${secs(s.endedAt, s.startedAt)} s`;
    case 'error':
      return `Failed: ${s.error}`;
  }
}
