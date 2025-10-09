# raspi-media-server

Raspberry Pi 4 (8GB) + OpenMediaVault(OMV) を前提に、NAS/動画/漫画/リモートアクセスを Docker Compose で統合する構成です。OS 用 SSD にシステムを集約し、USB3.0 ストレージをメディア保存に利用する前提で設計しています。

## システム構成方針
- **OS**: OMV 6 以降を SSD へインストールし、`omv-extras` で Docker/Compose v2 を有効化。
- **サービス**: Jellyfin (動画ライブラリ)、Komga (書籍・漫画)、Samba (ファイル共有・必要なら OMV ネイティブ機能でも可)、Tailscale (遠隔アクセス)。
- **ハードウェア要件**: Raspberry Pi 4 8GB、信頼性の高い USB3.0-SATA アダプタ、十分な容量の外付けストレージ。可能なら有線 LAN + 静的 IP。
- **権限管理**: すべてのコンテナは `UID/GID=1000` (pi ユーザー想定) で実行。OMV の共有フォルダ権限と整合を取る。

## ストレージ設計
- **OS 用 SSD**: `/opt/docker` 以下にコンテナ設定・キャッシュを配置 (可変: `CONFIG_ROOT`, `CACHE_ROOT`)。
- **データ用 USB3.0 ストレージ**: OMV が `/srv/dev-disk-by-uuid-XXXX/` にマウント。共有フォルダ例: `/srv/dev-disk-by-uuid-XXXX/media`。
- **Bind mount ポリシー**:
  - Jellyfin: `/media` に動画ライブラリ全体をマウント。
  - Komga: `/books` に漫画/書籍ディレクトリをマウント (既定で読み取り専用)。
  - Samba: 同じメディア共有を `/shares/media` として公開。OMV 標準 Samba を使う場合は本コンテナを無効化してもよい。
- 電源断対策としてセルフパワー USB ハブ利用を推奨。再起動後は OMV の「ファイルシステム」でマウント状態を確認。

## ネットワーク方針
- OMV で静的 IP を割り当て、ルーター側も DHCP 予約する。
- Tailscale はコンテナで稼働。サブネットルート広告が必要なら `TAILSCALE_EXTRA_ARGS` に `--advertise-routes` を指定。
- 外部公開はルーターのポート転送ではなく、Tailscale 経由を推奨。どうしても公開する場合は Nginx 等のリバースプロキシ + 認証を別途用意。

## セットアップ手順
1. **OMV 初期設定**
   - OMV を SSD へインストールし、管理 GUI で管理者パスワードを変更。
   - `omv-extras` → Docker/Compose/Portainer をインストール。
   - USB3.0 ストレージを接続し、`ストレージ > ファイルシステム` から EXT4 で初期化のうえマウント。
   - `アクセス権管理 > 共有フォルダ` で `media` (例: `/srv/dev-disk-by-uuid-XXXX/media`) を作成し、pi ユーザーに読み書き権限を付与。

2. **リポジトリ配置**
   - `git clone` もしくは本ディレクトリを OMV ホスト上の任意パスへ配置。
   - `.env.example` をコピーして `CONFIG_ROOT` や `MEDIA_ROOT` などを実環境に合わせて修正。
     ```bash
     cp .env.example .env
     nano .env
     ```

3. **コンテナ起動**
   - 初回はイメージ取得とディレクトリ作成を行う。
     ```bash
     docker compose pull
     docker compose up -d
     ```
   - Jellyfin: `http://<固定IP>:8096`
   - Komga: `http://<固定IP>:25600`
   - Samba: `\\<固定IP>\Media` (Windows) / `smb://<固定IP>/Media` (macOS)
   - Tailscale: `TAILSCALE_AUTHKEY` を設定するか、`docker compose exec tailscale tailscale up` でログイン。

4. **動作確認と調整**
   - Jellyfin でライブラリを2つ作成:
     - 「Videos Public」→ フォルダ `/media/video`
     - 「Videos Private」→ フォルダ `/media/utatane`
     必要に応じてユーザーごとにライブラリアクセスを制限。
   - Komga はライブラリルートを `/books` に設定。
   - Samba ユーザーで読み書きできるか確認。必要なら OMV 側 ACL を再調整。
   - Tailscale 管理画面でノード登録とサブネット設定を確認。

## ディレクトリ構成 (推奨)
```
/opt/docker
  ├─ jellyfin/config      # Jellyfin 設定・メタデータ
  ├─ jellyfin/cache       # Jellyfin キャッシュ（一部を別パスに出す場合は CACHE_ROOT を変更）
  ├─ komga/config         # Komga 設定・データベース
  └─ tailscale/state      # Tailscale 状態ファイル

/srv/dev-disk-by-uuid-XXXX/media
  ├─ video/               # 公開側の動画 (Jellyfin: /media/video)
  ├─ utatane/             # プライベート動画 (Jellyfin: /media/utatane)
  └─ manga/               # 漫画・書籍 (Komga: /books)
```
実際の UUID は `ls -al /srv` や OMV GUI で確認し、`.env` の `MEDIA_ROOT` / `VIDEOS_ROOT` / `PRIVATE_VIDEOS_ROOT` / `MANGA_ROOT` / `SAMBA_SHARE_PATH` を更新してください。

## 運用ノート
- Samba のデフォルトパスワード `changeme` は必ず変更。複数ユーザー運用時は OMV 標準の Samba 共有へ移行するほうが安全。
- Jellyfin のハードウェアトランスコードは Pi では負荷が高いため、基本はソフトウェア再生を想定。解像度やビットレートを事前変換しておくと安定。
- Komga のメタデータは `/books` 以下のフォルダ構造に依拠するため、命名規則を定めておく。
- 定期的に `docker compose pull` → `docker compose up -d` で更新。アップデート前に `docker compose logs` でエラーが無いか確認。
- バックアップは `CONFIG_ROOT` 配下とメディアストレージを別ドライブへ同期。最低でも設定ディレクトリは週次バックアップ推奨。

## ネクストステップ案
- 監視: Netdata や Prometheus Node Exporter を追加して温度/負荷を可視化。
- リバースプロキシ: Nginx Proxy Manager を追加し、HTTPS 経由でのアクセスに統一。
- 外部公開方針が固まり次第、ファイアウォールルールや Fail2ban をホスト側で設定。
