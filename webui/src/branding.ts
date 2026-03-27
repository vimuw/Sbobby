// App branding — change these to rename the app everywhere
export const APP_NAME = 'El Sbobinator';
export const APP_SHORT = 'Sbobinator';
export const APP_WINDOW_TITLE = 'El Sbobinator';
export const GITHUB_REPO = 'vimuw/El-Sbobinator';
export const GITHUB_URL = `https://github.com/${GITHUB_REPO}`;
export const GITHUB_RELEASES_URL = `${GITHUB_URL}/releases/latest`;
export const GITHUB_API_RELEASES_URL = `https://api.github.com/repos/${GITHUB_REPO}/releases/latest`;
export const KOFI_URL = 'https://ko-fi.com/vimuw';

// Injected at build time by Vite from package.json — do not hardcode here.
declare const __APP_VERSION__: string;
export const APP_VERSION: string = typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : 'v0.0.0';
