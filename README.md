# raspi-media-server

Raspberry Pi 4 (8GB) + OpenMediaVault(OMV) を前提に、NAS/動画/漫画/リモートアクセスを Docker Compose で統合する構成です。OS 用 SSD にシステムを集約し、USB3.0 ストレージをメディア保存に利用する前提で設計しています。

## システム構成方針
- **OS**: OMV 6 以降を SSD へインストールし、`omv-extras` で Docker/Compose v2 を有効化。
- **サービス**: Jellyfin (動画ライブラリ)、Komga (書籍・漫画)、Tailscale (遠隔アクセス)。ファイル共有は OMV 標準の SMB を使用。
- **ハードウェア要件**: Raspberry Pi 4 8GB、信頼性の高い USB3.0-SATA アダプタ、十分な容量の外付けストレージ。有線 LAN + 静的 IP。
- **権限管理**: すべてのコンテナは `UID/GID=1000`（手動で作成した管理ユーザーを想定）で実行。OMV の共有フォルダ権限と整合を取る。

## ストレージ設計
- **OS 用 SSD**: `/opt/docker` 以下にコンテナ設定・キャッシュを配置 (可変: `CONFIG_ROOT`, `CACHE_ROOT`)。
- **データ用 USB3.0 ストレージ**: OMV が `/srv/dev-disk-by-uuid-XXXX/` にマウント。共有フォルダ例: `/srv/dev-disk-by-uuid-XXXX/media`。
- **Bind mount ポリシー**:
  - Jellyfin: `/media/video`（共有用）と `/utatane/video`（個人用）をマウント（既定で読み取り専用）。
  - Komga: まずは `/media/books`（共有用）のみをマウント。個人用を追加したい場合は `docker-compose.yml` のコメントを外し `/utatane/books` を有効化します。
  - ファイル共有は OMV の SMB 共有で提供（本リポジトリに Samba コンテナは含めません）。
- 電源断対策としてセルフパワー USB ハブ利用を推奨。再起動後は OMV の「ファイルシステム」でマウント状態を確認。

## ネットワーク方針
- OMV で静的 IP を割り当て、ルーター側も DHCP 予約する。
- Tailscale はコンテナで稼働。サブネットルート広告が必要なら `TAILSCALE_EXTRA_ARGS` に `--advertise-routes` を指定。
- 外部公開はルーターのポート転送ではなく、Tailscale 経由を推奨。どうしても公開する場合は Nginx 等のリバースプロキシ + 認証を別途用意。

### iOS (Panels) からの利用
- 方式: Tailscale VPN 経由で Komga の OPDS を参照。
- 手順:
  1) iOS に Tailscale と Panels をインストールし、Tailscale にログイン。
  2) Komga で利用するユーザーを作成（読み取り専用でも可）。
  3) Panels で OPDS カタログを追加。
     - URL (MagicDNS を有効にしている場合): `http://raspi-media:25600/opds`
     - URL (MagicDNS なし): `http://<Tailscaleの100.x.x.x>:25600/opds`
       - 100.x の確認: `docker compose exec tailscale tailscale ip -4`
     - 認証: Komga のユーザー名/パスワード
  4) 以後、iOS で Tailscale 接続中は Panels から Komga にアクセス可能。
  - 備考: インターネット直公開は非推奨。HTTPS が必要なら Cloudflare Tunnel や Nginx Proxy Manager を別途導入。

### アクセスURL（ポート分離・Tailscale前提）
- ホスト名は共通（例: `raspi-media`）、サービスごとにポートで分離します。
- Jellyfin (動画): `http://raspi-media:8096`
  - iOS 公式アプリからも同URLを指定で接続可
- Komga (Web UI): `http://raspi-media:25600`
- Komga (OPDS): `http://raspi-media:25600/opds`
- MagicDNS を使わない場合は `raspi-media` を Tailscale の 100.x.x.x アドレスに置き換えてください。

### ローカルSMBアクセス（OMV 標準）
Windows エクスプローラー:
  - 共有 `media`: `\\\\<固定IP>\\media`（認証必須）
  - 共有 `utatane`: `\\\\<固定IP>\\utatane`（認証必須）
macOS Finder:
  - `smb://<固定IP>/media`（認証必須）, `smb://<固定IP>/utatane`（認証必須）

## セットアップ手順
1. **Raspberry Pi OS / OMV 事前準備**
   - Raspberry Pi OS Lite (64-bit, Debian 12 Bookworm ベース) をクリーンインストールし、初期設定で **pi とは別の管理ユーザー** を手動作成して SSH を有効化する。
   - 手動で作成した管理ユーザーで SSH 接続し、`whoami` が期待どおりになっていることと `sudo` が利用できることを確認する（Playbook はこのユーザーで実行する）。
   - UID/GID の数値は気にしなくてよい。Playbook 実行時に自動的に 1000/1000 に揃え、ホーム配下の所有権も修正する。
   - OMV 6 以降を SSD へインストールし、管理 GUI の初期設定（管理者パスワード変更など）を完了する。
   - `omv-extras` → Docker/Compose/Portainer をインストール。
   - USB3.0 ストレージを接続し、`ストレージ > ファイルシステム` から EXT4 で初期化のうえマウント。
   - `アクセス権管理 > 共有フォルダ` で `media` (例: `/srv/dev-disk-by-uuid-XXXX/media`) と `utatane` (例: `/srv/dev-disk-by-uuid-XXXX/utatane`) を作成し、手動で作成した管理ユーザーに必要な権限（読取/必要なら書込）を付与する。

2. **リポジトリ配置**
 - `git clone` もしくは本ディレクトリを OMV ホスト上の任意パスへ配置。
  - `.env` は Ansible テンプレート (`ansible/templates/dotenv.j2`) から生成します。先に `ansible/group_vars/all.yml` の `dotenv` 値を環境に合わせて編集してください。
  - 初期生成や変更反映は Playbook の `dotenv` タグで実施します。
    ```bash
    ansible-playbook -i ansible/inventory.ini ansible/raspi_setup.yml --tags dotenv
    ```
    Playbook 全体を実行する場合はタグ指定なしでも `.env` が同時に配置されます。

### Ansible による Raspberry Pi 初期セットアップ
- Playbook: `ansible/raspi_setup.yml`
  - APT の更新、タイムゾーン/ホスト名設定、`pi` ユーザーの削除、SSH Hardening、UFW/Fail2ban 導入、unattended-upgrades（セキュリティリポジトリのみ自動適用、OMV/カーネル/ブートローダーはブラックリスト）の設定、OMV 未導入時のインストーラ実行までを自動化します。
  - `pi` ユーザー削除後に、**手動で作成した管理ユーザーの UID/GID を 1000/1000 に自動で揃え、ホームディレクトリ配下の所有権も調整**します。1000 が別ユーザーで占有されている場合は Playbook が fail するので、先に手動で整理してください。
  - **必ず手動で作成した管理ユーザーで SSH 接続して実行してください。`pi` ユーザーで実行すると Playbook の途中で接続が切れます。**
  - `community.general` コレクション（`ansible-galaxy collection install community.general`）を事前に導入しておくこと。
  - セキュリティリポジトリのみ無人適用し、それ以外（OMV、カーネル、ブートローダー等）はブラックリストで除外しています。機能アップデートは `sudo apt update && sudo apt upgrade --with-new-pkgs` を手動で実行し、適用前に changelog を確認してください。
- インベントリ例 (ホスト側で `ansible/inventory.ini` などを別途作成):
  ```ini
  [raspi]
  raspi-media ansible_host=192.168.1.10 ansible_user=mediaadmin
  ```
- 実行例:
  ```bash
  export RASPI_TARGET_HOSTS=raspi
  export RASPI_SET_HOSTNAME=raspi-media
  ansible-playbook -i ansible/inventory.ini ansible/raspi_setup.yml
  ```
  - `--check` や `--diff` オプションを活用し、変更内容を必ず確認してください。
  - Playbook 実行前に手動作成した管理ユーザーで新たに SSH セッションを貼り直し、`whoami` が期待どおりであることを確認したうえで実行してください。

3. **コンテナ起動**
   - 初回はイメージ取得とディレクトリ作成を行う。
     ```bash
     docker compose pull
     docker compose up -d
     ```
   - Jellyfin: `http://<固定IP>:8096`
   - Komga: `http://<固定IP>:25600`
   - SMB 共有（OMV 標準）: Windows `\\<固定IP>\<共有名>` / macOS `smb://<固定IP>/<共有名>`
   - Tailscale: `TAILSCALE_AUTHKEY` を設定しておくか、`docker compose exec tailscale tailscale up` でログイン。
     - MagicDNS を有効化すると `http://raspi-media:25600` のように名前でアクセス可能。

4. **動作確認と調整**
    - Jellyfin: ライブラリを2つ作成。
      - 「Videos」→ フォルダ `/media/video`
      - 「Videos Utatane」→ フォルダ `/utatane/video`
      ユーザーごとに「Videos Utatane」の可視性を制御。
   - Komga: まずは公開用のみ作成（シンプル運用）。
     - 「Manga」→ フォルダ `/media/books`（共有）
     - 私用が必要になったら「Manga Utatane」→ `/utatane/books` を追加し、ユーザーごとに可視性を制御。
   - OMV の SMB 共有で `media` と `utatane` の読み書きを確認。必要なら OMV 側 ACL を再調整。
   - Tailscale 管理画面でノード登録とサブネット設定を確認。

## ディレクトリ構成 (推奨)
```
/opt/docker
  ├─ jellyfin/config      # Jellyfin 設定・メタデータ
  ├─ jellyfin/cache       # Jellyfin キャッシュ（一部を別パスに出す場合は CACHE_ROOT を変更）
  ├─ komga/config         # Komga 設定・データベース
  └─ tailscale/state      # Tailscale 状態ファイル

/srv/dev-disk-by-uuid-XXXX/media
  ├─ video/               # 共有(家族)動画 (Jellyfin: /media/video, SMB: \\video)
  ├─ picture/             # 共有(家族)写真 (SMB: \\picture、アプリ連携なし/任意)
  └─ manga/               # 共有(家族)漫画 (Komga: /media/books)

/srv/dev-disk-by-uuid-XXXX/utatane
  ├─ video/               # 非公開動画 (Jellyfin: /utatane/video)
  ├─ picture/             # 非公開写真 (SMB: \\utatane\picture、アプリ連携なし/任意)
  └─ manga/               # 非公開漫画 (Komga: /utatane/books)
```
実際の UUID は `ls -al /srv` や OMV GUI で確認し、`ansible/group_vars/all.yml` の `dotenv` → `MEDIA_ROOT` / `VIDEOS_ROOT` / `PRIVATE_VIDEOS_ROOT` / `PICTURE_ROOT` / `MANGA_PUBLIC_ROOT` / `MANGA_PRIVATE_ROOT` を更新してから `ansible-playbook ... --tags dotenv` で再生成してください（PICTURE は SMB 共有のみで使用）。

## 運用ノート
- Jellyfin のハードウェアトランスコードは Pi では負荷が高いため、基本はソフトウェア再生を想定。解像度やビットレートを事前変換しておくと安定。
- Komga のメタデータはライブラリで指定したパス（例: `/media/books` や `/utatane/books`）以下の構造に依拠するため、命名規則を定めておく。
- 定期的に `docker compose pull` → `docker compose up -d` で更新。アップデート前に `docker compose logs` でエラーが無いか確認。
- バックアップは `CONFIG_ROOT` 配下とメディアストレージを別ドライブへ同期。最低でも設定ディレクトリは週次バックアップ推奨。

## OMV での SMB 共有作成（推奨運用）
- 共有フォルダを作成（アクセス方針）
  - media → 実体 `/srv/.../media`（認証必須、家族全員に読取/必要なら書込。配下に video/picture/manga）
  - utatane → 実体 `/srv/.../utatane`（認証必須、許可ユーザーのみ。配下に video/picture/manga）
- 権限/ACL（OMV GUI: アクセス権管理 → 共有フォルダ → 権限/ACL）
  - Jellyfin/Komga 実行ユーザー（UID/GID=1000）に少なくとも読取付与（Jellyfin は video/utatane、Komga は manga）
  - utatane は対象ユーザー（または専用グループ）のみに読取/書込権限を付与し、ゲストは拒否
  - LAN 限定にする場合は共有の「追加オプション」に以下例を指定
    - hosts allow = 192.168.0.0/16 10.0.0.0/8
    - hosts deny = 0.0.0.0/0

## ネクストステップ案
- 監視: Netdata や Prometheus Node Exporter を追加して温度/負荷を可視化。
- リバースプロキシ: Nginx Proxy Manager を追加し、HTTPS 経由でのアクセスに統一。
- 外部公開方針が固まり次第、ファイアウォールルールや Fail2ban をホスト側で設定。
