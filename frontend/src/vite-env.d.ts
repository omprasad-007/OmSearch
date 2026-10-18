/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly [key: string]: any;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare module 'react' {
  export function useState<T = any>(initialState?: T | (() => T)): [T, (action: T | ((prevState: T) => T)) => void];
  export function useEffect(effect: () => void | (() => void), deps?: any[]): void;
  export function useRef<T = any>(initialValue?: T): { current: T };
  export function useMemo<T = any>(factory: () => T, deps: any[]): T;
  export function useCallback<T extends (...args: any[]) => any>(callback: T, deps: any[]): T;
  export const Fragment: any;
  export type FC<P = {}> = (props: P) => any;
  export type ReactNode = any;
  export type ReactElement = any;
  export type FormEvent<T = any> = any;
  export type KeyboardEvent<T = any> = any;
  export type ChangeEvent<T = any> = any;
  export type MouseEvent<T = any> = any;
  const React: any;
  export default React;
}

declare namespace React {
  export type FC<P = {}> = (props: P) => any;
  export type ReactNode = any;
  export type ReactElement = any;
  export type FormEvent<T = any> = any;
  export type KeyboardEvent<T = any> = any;
  export type ChangeEvent<T = any> = any;
  export type MouseEvent<T = any> = any;
  export function useState<T = any>(initialState?: T | (() => T)): [T, (action: T | ((prevState: T) => T)) => void];
  export function useEffect(effect: () => void | (() => void), deps?: any[]): void;
  export function useRef<T = any>(initialValue?: T): { current: T };
}

declare module 'react/jsx-runtime' {
  export const jsx: any;
  export const jsxs: any;
  export const Fragment: any;
}

declare module 'react/jsx-dev-runtime' {
  export const jsxDEV: any;
  export const Fragment: any;
}

declare module 'lucide-react' {
  export const X: any;
  export const Activity: any;
  export const Cpu: any;
  export const Play: any;
  export const Pause: any;
  export const RefreshCw: any;
  export const ShieldCheck: any;
  export const Database: any;
  export const Layers: any;
  export const Compass: any;
  export const HardDrive: any;
  const icons: any;
  export default icons;
}
