// Mock mode wiring (VITE_MOCK=1 only). Imported dynamically from main.tsx so the real build
// does not depend on it at runtime.
import { installMock } from '../api';
import { mockModelUrl, mockTransport } from './backend';

export function install() {
  installMock((method, path, body) => mockTransport(method, path, body), mockModelUrl);
}
