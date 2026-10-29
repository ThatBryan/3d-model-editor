// Comment-thread summaries for the Comments list. Pure, unit tested.
import type { Message, Pin } from '../types';

export interface PinSummary {
  first: string;
  latest: Message | null;
  /** Messages after the first one. */
  replies: number;
  lastAt: string | null;
}

export function pinSummary(pin: Pin): PinSummary {
  const latest = pin.messages.length ? pin.messages[pin.messages.length - 1] : null;
  return { first: pin.messages[0]?.text ?? '', latest, replies: Math.max(0, pin.messages.length - 1), lastAt: latest?.at ?? null };
}

/** "29 Oct, 08:39" in local time; empty for a missing or bad timestamp. */
export function shortTime(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const day = d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
  const time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false });
  return `${day}, ${time}`;
}

/** Pins numbered as created (the number on the model), split into still-open and resolved. */
export function groupPins(pins: Pin[]): { open: { pin: Pin; n: number }[]; resolved: { pin: Pin; n: number }[] } {
  const numbered = pins.map((pin, i) => ({ pin, n: i + 1 }));
  return {
    open: numbered.filter((x) => x.pin.status !== 'resolved'),
    resolved: numbered.filter((x) => x.pin.status === 'resolved'),
  };
}
