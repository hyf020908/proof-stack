import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { useAuthStore } from "../auth/store";
import { useUiStore } from "../stores/ui";

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => true,
  }),
});

vi.stubGlobal("ResizeObserver", ResizeObserverMock);
vi.stubGlobal("scrollTo", vi.fn());

Object.defineProperties(HTMLElement.prototype, {
  clientWidth: { configurable: true, get: () => 800 },
  clientHeight: { configurable: true, get: () => 400 },
});

HTMLElement.prototype.getBoundingClientRect = () => ({
  x: 0,
  y: 0,
  top: 0,
  left: 0,
  right: 800,
  bottom: 400,
  width: 800,
  height: 400,
  toJSON: () => ({}),
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.localStorage.clear();
  useAuthStore.setState({ accessToken: null, refreshToken: null, user: null, hydrated: true });
  useUiStore.setState({ theme: "system", sidebarOpen: false });
});
