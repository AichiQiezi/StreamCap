import { Film, Moon, Radio, Settings2, Sun } from "lucide-react";
import { useEffect, useState, useSyncExternalStore } from "react";
import { Toaster } from "sonner";
import { cx, Tip, TipProvider } from "./components/ui";
import { bytes } from "./lib/format";
import { connectLive, useStore } from "./lib/store";
import { LibraryPage } from "./pages/library";
import { RoomsPage } from "./pages/rooms";
import { SettingsPage } from "./pages/settings";

const ROUTES = {
  rooms: { label: "直播间", icon: Radio, Page: RoomsPage },
  library: { label: "录像", icon: Film, Page: LibraryPage },
  settings: { label: "设置", icon: Settings2, Page: SettingsPage },
} as const;
type Route = keyof typeof ROUTES;

const subscribeHash = (cb: () => void) => {
  window.addEventListener("hashchange", cb);
  return () => window.removeEventListener("hashchange", cb);
};
const readRoute = (): Route => {
  const r = location.hash.replace(/^#\/?/, "") as Route;
  return r in ROUTES ? r : "rooms";
};

function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("sc-theme", dark ? "dark" : "light");
    } catch {
      /* storage unavailable */
    }
  }, [dark]);
  return [dark, setDark] as const;
}

function Logo() {
  return (
    <svg viewBox="0 0 32 32" className="size-7" aria-hidden>
      <rect width="32" height="32" rx="8" className="fill-fg" />
      <circle cx="16" cy="16" r="8.5" fill="none" className="stroke-bg" strokeWidth="2" />
      <circle cx="16" cy="16" r="4" fill="var(--rec)" />
    </svg>
  );
}

function Sidebar({ route }: { route: Route }) {
  const conn = useStore((s) => s.conn);
  const disk = useStore((s) => s.disk);
  const recordingCount = useStore((s) => Object.values(s.recs).filter((r) => r.state === "recording").length);
  const [dark, setDark] = useTheme();
  const used = disk ? 1 - disk.free / disk.total : 0;

  return (
    <aside className="flex w-[60px] shrink-0 flex-col border-r border-line bg-surface/60 px-2.5 pt-4 pb-3 lg:w-[216px] lg:px-3">
      <div className="flex items-center gap-2.5 px-1 pb-6 lg:px-2">
        <Logo />
        <span className="text-[15px] font-semibold tracking-[-0.02em] max-lg:hidden">StreamCap</span>
      </div>
      <nav className="space-y-0.5">
        {(Object.keys(ROUTES) as Route[]).map((key) => {
          const { label, icon: Icon } = ROUTES[key];
          return (
            <a
              key={key}
              href={`#/${key}`}
              title={label}
              className={cx(
                "relative flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-[13.5px] transition max-lg:justify-center",
                route === key ? "bg-surface-2 font-medium text-fg" : "text-fg-2 hover:bg-surface-2/60 hover:text-fg",
              )}
            >
              <Icon className="size-4 shrink-0" strokeWidth={route === key ? 2.2 : 1.8} />
              <span className="max-lg:hidden">{label}</span>
              {key === "rooms" && recordingCount > 0 && (
                <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-rec/12 px-1.5 py-px font-mono text-[11px] font-medium text-rec tabular max-lg:absolute max-lg:-top-1 max-lg:-right-1 max-lg:px-1">
                  <span className="size-1.5 rounded-full bg-rec animate-rec" />
                  {recordingCount}
                </span>
              )}
            </a>
          );
        })}
      </nav>

      <div className="mt-auto space-y-3">
        {disk && (
          <Tip label={disk.path} side="right">
            <div className="rounded-lg border border-line bg-surface px-3 py-2.5 max-lg:hidden">
              <div className="flex justify-between text-[11.5px]">
                <span className="text-fg-3">磁盘</span>
                <span className="font-mono text-fg-2 tabular">{bytes(disk.free)} 可用</span>
              </div>
              <div className="mt-2 h-1 overflow-hidden rounded-full bg-surface-3">
                <div
                  className="h-full rounded-full"
                  style={{ width: `${Math.round(used * 100)}%`, background: used > 0.9 ? "var(--warn)" : "var(--fg-3)" }}
                />
              </div>
            </div>
          </Tip>
        )}
        <div className="flex items-center justify-between px-1 max-lg:flex-col max-lg:gap-3">
          <Tip label={conn === "open" ? "已连接录制服务" : conn === "connecting" ? "正在连接…" : "已断开，正在重连"} side="right">
            <span className="inline-flex items-center gap-1.5 text-[11.5px] text-fg-3">
              <span className={cx("size-1.5 rounded-full", conn === "open" ? "bg-ok" : conn === "connecting" ? "bg-warn animate-rec" : "bg-err")} />
              <span className="max-lg:hidden">{conn === "open" ? "在线" : conn === "connecting" ? "连接中" : "离线"}</span>
            </span>
          </Tip>
          <Tip label={dark ? "切换到浅色" : "切换到深色"} side="right">
            <button
              onClick={() => setDark(!dark)}
              aria-label="切换主题"
              className="rounded-md p-1.5 text-fg-3 transition hover:bg-surface-2 hover:text-fg"
            >
              {dark ? <Sun className="size-3.5" /> : <Moon className="size-3.5" />}
            </button>
          </Tip>
        </div>
      </div>
    </aside>
  );
}

export function App() {
  const route = useSyncExternalStore(subscribeHash, readRoute);
  useEffect(() => connectLive(), []);
  const { Page, label } = ROUTES[route];

  useEffect(() => {
    document.title = `${label} · StreamCap`;
  }, [label]);

  return (
    <TipProvider>
      <div className="flex h-full">
        <Sidebar route={route} />
        <main className="min-w-0 flex-1 overflow-y-auto">
          <Page />
        </main>
      </div>
      <Toaster
        position="bottom-right"
        toastOptions={{
          className: "!bg-surface !text-fg !border-line !shadow-xl !rounded-xl !text-[13px] !font-sans",
        }}
      />
    </TipProvider>
  );
}
