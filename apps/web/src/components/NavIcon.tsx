const paths: Record<string, string> = {
  home: "M3 10 12 3l9 7v11h-6v-7H9v7H3Z",
  chart: "M4 3v18h17M8 16v-4m5 4V7m5 9v-6",
  file: "M6 3h8l4 4v14H6ZM14 3v5h4M9 12h6m-6 4h6",
  users:
    "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm8 1a4 4 0 0 1 0 8m3 9v-2a4 4 0 0 0-3-4",
  chat: "M4 4h16v12H9l-5 5ZM8 8h8m-8 4h5",
  upload: "M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5",
  alert: "m12 3 10 18H2ZM12 9v5m0 3v1",
  tree: "M12 3v7M5 10h14M5 10v5m14-5v5M2 15h6v6H2Zm14 0h6v6h-6ZM9 3h6v4H9Z",
  menu: "M4 6h16M4 12h16M4 18h16",
};
export function NavIcon({ name }: { name: string }) {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name] || paths.file} />
    </svg>
  );
}
