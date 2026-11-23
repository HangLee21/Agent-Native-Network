# EmboNet 品牌素材

来源：用户 2026-11-07 提供的 8 个 SVG（文件原样，未改）和《EmboNet Logo Sheet》v1.0。

- `embonet-lockup-*`：图形加字；`embonet-mark-*`：只有图形。每套四种色调：color（浅色底）、reverse（深色底）、mono（单色）、monorev（单色反白）。
- 颜色：Embo Teal `#16888A`（旋翼、机械臂、"Net"），Graphite `#23292F`（机身、腿、"Embo"）；Teal Light `#3FC1C0` 只用在反白版。
- 最小尺寸：带字版 24 px 高、120 px 宽；只有图形 16 px 高。
- 四周留白不小于图形高度的 1/4。
- 不要拉伸、旋转、改色、加阴影；彩色版不要放在中间调的底色上。
- 字体 Poppins 400，写法固定为 EmboNet（不全大写）。lockup SVG 里的字没有嵌字体，所以界面上用 mark SVG + HTML 文字，Poppins 400 拉丁子集打包在 `../fonts/`（SIL OFL 1.1，许可证 `../fonts/Poppins-OFL.txt`，来自 npm 包 @fontsource/poppins 5.3.0）。
- 浏览器标签页图标 `public/embonet-icon.svg`：规范里的 App icon 做法，青色圆角底（`#16888A`，112 px 圆角 26）上放白色 mark（monorev）。不用旧名字 `favicon.svg`：旧的无人机图标也叫这个名字，浏览器会一直用缓存里的旧图。另有 `embonet-icon-32.png`（不支持 SVG 图标的浏览器，例如部分 Safari）和 `apple-touch-icon.png`（180 px，方形满底，系统自己裁圆角），都是用 Chrome 无头模式从这个 SVG 渲染的；改了 SVG 要一起重新生成。
