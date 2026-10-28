// Job polling helper: drives the pure state machine in jobs.ts against GET /api/jobs/{id}.
import { api, errorText } from '../api';
import { nextDelayMs, pollReducer, type PollState } from './jobs';

export interface PollOptions<R> {
  onUpdate?: (s: PollState<R>) => void;
  signal?: AbortSignal;
}

/** Poll a job until it finishes. Resolves with the result; rejects with the job's error. */
export async function pollJob<R = unknown>(jobId: string, opts: PollOptions<R> = {}): Promise<R> {
  let s: PollState<R> = pollReducer<R>({ phase: 'idle' }, { type: 'start', jobId, now: Date.now() });
  opts.onUpdate?.(s);
  for (;;) {
    if (opts.signal?.aborted) throw new DOMException('Stopped watching the job', 'AbortError');
    try {
      const job = await api.job<R>(jobId);
      s = pollReducer(s, { type: 'response', job, now: Date.now() });
    } catch (e) {
      s = pollReducer(s, { type: 'network_error', message: errorText(e), now: Date.now() });
    }
    opts.onUpdate?.(s);
    if (s.phase === 'done') return s.result;
    if (s.phase === 'error') throw new Error(s.error);
    await new Promise((r) => setTimeout(r, nextDelayMs(s, Date.now())));
  }
}
