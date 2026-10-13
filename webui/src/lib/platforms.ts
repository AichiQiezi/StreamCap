/**
 * Platform key <-> display name mapping. Mirrors the backend
 * `get_platform_info` in `app/core/platforms/platform_handlers/__init__.py`
 * so the add-form can recognise a URL before it is sent to the server.
 */

const URL_MATCHERS: [substr: string, key: string][] = [
  ["douyin.com/", "douyin"],
  ["https://www.tiktok.com/", "tiktok"],
  ["https://live.kuaishou.com/", "kuaishou"],
  ["https://www.huya.com/", "huya"],
  ["https://www.douyu.com/", "douyu"],
  ["https://www.yy.com/", "yy"],
  ["https://live.bilibili.com/", "bilibili"],
  ["https://www.xiaohongshu.com/", "xiaohongshu"],
  ["xhslink.com/", "xhs"],
  ["https://www.bigo.tv/", "bigo"],
  ["https://app.blued.cn/", "blued"],
  ["sooplive.co.kr/", "sooplive"],
  ["sooplive.com/", "sooplive"],
  ["play.sooplive.com/", "sooplive"],
  ["cc.163.com/", "netease"],
  ["qiandurebo.com/", "qiandurebo"],
  ["pandalive.co.kr/", "pandalive"],
  ["fm.missevan.com/", "maoerfm"],
  ["winktv.co.kr/", "winktv"],
  ["flextv.co.kr/", "flextv"],
  ["ttinglive.com/", "flextv"],
  ["look.163.com/", "look"],
  ["popkontv.com/", "popkontv"],
  ["twitcasting.tv/", "twitcasting"],
  ["live.baidu.com/", "baidu"],
  ["weibo.com/", "weibo"],
  ["kugou.com/", "kugou"],
  ["twitch.tv/", "twitch"],
  ["liveme.com/", "liveme"],
  ["huajiao.com/", "huajiao"],
  ["7u66.com/", "liuxing"],
  ["showroom-live.com/", "showroom"],
  ["live.acfun.cn/", "acfun"],
  ["tlclw.com/", "changliao"],
  ["ybw1666.com/", "yingbo"],
  ["inke.cn/", "inke"],
  ["zhihu.com/", "zhihu"],
  ["chzzk.naver.com/", "chzzk"],
  ["haixiutv.com/", "haixiu"],
  ["vvxqiu.com/", "vvxq"],
  ["17.live/", "17live"],
  ["lang.live/", "lang"],
  ["m.pp.weimipopo.com/", "piaopiao"],
  [".6.cn/", "6room"],
  ["lehaitv.com/", "lehai"],
  ["h.catshow168.com/", "catshow"],
  ["live.shopee", "shopee"],
  [".shp.", "shopee"],
  ["youtube.com/", "youtube"],
  ["tb.cn", "taobao"],
  ["tbzb.taobao.com", "taobao"],
  ["3.cn", "jd"],
  ["faceit.com", "faceit"],
  ["lailianjie.com", "lianjie"],
  ["miguvideo.com/", "migu"],
  ["imkktv.com/", "laixiu"],
  ["picarto.tv", "picarto"],
  ["xcqrkj.com", "xindongrebo"],
  [".m3u8", "custom"],
  [".flv", "custom"],
];

export const PLATFORM_NAMES: Record<string, string> = {
  douyin: "抖音直播",
  tiktok: "TikTok直播",
  kuaishou: "快手直播",
  huya: "虎牙直播",
  douyu: "斗鱼直播",
  yy: "YY直播",
  bilibili: "B站直播",
  xiaohongshu: "小红书直播",
  xhs: "小红书直播",
  bigo: "Bigo直播",
  blued: "Blued直播",
  sooplive: "SOOP",
  netease: "网易CC直播",
  qiandurebo: "千度热播",
  pandalive: "PandaTV",
  maoerfm: "猫耳FM直播",
  winktv: "WinkTV",
  flextv: "FlexTV",
  look: "Look直播",
  popkontv: "PopkonTV",
  twitcasting: "TwitCasting",
  baidu: "百度直播",
  weibo: "微博直播",
  kugou: "酷狗直播",
  twitch: "TwitchTV",
  liveme: "LiveMe",
  huajiao: "花椒直播",
  liuxing: "流星直播",
  showroom: "ShowRoom",
  acfun: "Acfun",
  changliao: "畅聊直播",
  yingbo: "音播直播",
  yinbo: "音播直播",
  inke: "映客直播",
  zhihu: "知乎直播",
  chzzk: "CHZZK",
  haixiu: "嗨秀直播",
  vvxq: "VV星球",
  "17live": "17Live",
  lang: "浪Live",
  piaopiao: "漂漂直播",
  "6room": "六间房直播",
  lehai: "乐嗨直播",
  catshow: "花猫直播",
  shopee: "Shopee",
  youtube: "YouTube",
  taobao: "淘宝直播",
  jd: "京东直播",
  faceit: "Faceit",
  lianjie: "连接直播",
  migu: "咪咕直播",
  laixiu: "来秀直播",
  picarto: "Picarto",
  xindongrebo: "心动热播",
  custom: "自定义录制",
};

/** Platform keys that accept a cookie, same order as the desktop settings tab. */
export const COOKIE_PLATFORMS = [
  "douyin", "tiktok", "kuaishou", "huya", "douyu", "yy", "bilibili", "xhs",
  "bigo", "blued", "soop", "netease", "qiandurebo", "pandalive", "maoerfm",
  "winktv", "flextv", "look", "popkontv", "twitcasting", "baidu", "weibo",
  "kugou", "twitch", "liveme", "huajiao", "liuxing", "showroom", "acfun",
  "changliao", "yinbo", "inke", "zhihu", "chzzk", "haixiu", "vvxq", "17live",
  "lang", "piaopiao", "6room", "lehai", "catshow", "shopee", "youtube",
  "taobao", "jd",
];

/** Display name for a platform key, falling back to the server-sent name or the key itself. */
export function platformName(key: string | null | undefined, fallback?: string | null): string {
  if (key && PLATFORM_NAMES[key]) return PLATFORM_NAMES[key];
  return fallback || key || "未知平台";
}

/** Stable accent color per platform key. */
export function platformColor(key: string | null | undefined): string {
  const s = key || "?";
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360;
  return `hsl(${h} 62% 52%)`;
}

/** Match a room URL to a platform key (first match wins, like the backend). */
export function detectPlatform(url: string): string | null {
  const lower = url.trim().toLowerCase();
  for (const [substr, key] of URL_MATCHERS) {
    if (lower.includes(substr)) return key;
  }
  return null;
}
