/**
 * pages/index.js —— 页面注册表（id → 模块）
 *
 * 步骤表（steps.js）里的每个 id 都必须在这里有一个模块；探针会断言两边一致。
 */

import welcome from './welcome.js';
import network from './network.js';
import disk from './disk.js';
import account from './account.js';
import summary from './summary.js';
import confirm from './confirm.js';
import progress from './progress.js';
import finish from './finish.js';
import locale from './locale.js';
import keymap from './keymap.js';
import timezone from './timezone.js';
import hostname from './hostname.js';

export const PAGES = {
  welcome,
  network,
  disk,
  account,
  summary,
  confirm,
  progress,
  finish,
  locale,
  keymap,
  timezone,
  hostname,
};
