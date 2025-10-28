# raspi-media-server

Raspberry Pi 4 (8GB) + OpenMediaVault(OMV) を前提に、NAS/動画/漫画/リモートアクセスを Docker Compose で統合する構成です。OS 用 SSD にシステムを集約し、USB3.0 ストレージをメディア保存に利用する前提で設計しています。

## システム構成方針
- **OS**: Raspberry Pi OS Lite (64-bit, Debian 12 Bookworm ベース)。この構成では OMV 7 (Sandworm) を導入し、`omv-extras` で Docker/Compose v2 を有効化します。
  - 注意: OMV のメジャーバージョンは基盤の Debian に依存します。
  - Docker は Ansible が `omv-extras` 経由で自動的に有効化します（`omv-env` + `omv-salt deploy`）。
- **サービス**:
  - Jellyfin (家族共有動画)
  - Komga (家族共有漫画)
  - Stash (個人用メディア管理・視聴)
  - Tailscale (遠隔アクセス)
  - ファイル共有は OMV 標準の SMB を使用
- **ハードウェア要件**: Raspberry Pi 4 8GB、信頼性の高い USB3.0-SATA アダプタ、十分な容量の外付けストレージ。有線 LAN + 静的 IP。
- **権限管理**: すべてのコンテナは `UID/GID=1000`（手動で作成した管理ユーザーを想定）で実行。OMV の共有フォルダ権限と整合を取る。

## プロビジョニング方針と順序（重要）
- 原則: ストレージのマウントと共有フォルダは OMV が一元管理する（fstab 直書きや手動 mount は禁止）。OMV の設定DBに反映し、`omv-salt deploy run fstab` で適用する。
- 実行順（Play 単位）
  1) `raspi_bootstrap`: ベースOS調整＋OMV導入（SSH再接続を伴う）
  2) `raspi_post_omv`: 管理ユーザー整備、.env 生成、OMV-Extras 導入
  3) `omv_storage`: ディスク/ファイルシステムのマウント存在検証と初期ディレクトリ作成
  4) `omv_config`: OMV の共有フォルダ（SharedFolder）作成と SMB 共有の作成/更新
  5) `services_deploy`: Docker エンジン導入＋Compose で Jellyfin/Komga/Stash/Tailscale 起動
  6) `services_config`（任意）: Jellyfin/Komga/Stash の初期設定を最小限自動化

補足: `omv_storage` はまずマウント存在検証とディレクトリ初期化のみ対応（共有フォルダ/SMB/NFS は段階的に追加予定）。

## ストレージ設計
- **OS 用 SSD**: `/opt/docker` 以下にコンテナ設定・キャッシュを配置 (可変: `CONFIG_ROOT`, `CACHE_ROOT`)。
- **データ用 USB3.0 ストレージ**: OMV が `/srv/dev-disk-by-uuid-XXXX/` にマウント。共有フォルダは `media` (家族共有) と `utatane` (個人用) の2本柱構成。
- **Bind mount ポリシー**:
  - Jellyfin: `/media/video` のみマウント（家族共有動画、読み取り専用）。
  - Komga: `/media/manga` のみマウント（家族共有漫画、読み取り専用）。
  - Stash: `/utatane` 全体をマウント（個人用メディアの管理・視聴）。
  - ファイル共有は OMV の SMB 共有で提供（本リポジトリに Samba コンテナは含めません）。
- 電源断対策としてセルフパワー USB ハブ利用を推奨。再起動後は OMV の「ファイルシステム」でマウント状態を確認。

## ネットワーク方針
- OMV で静的 IP を割り当て、ルーター側も DHCP 予約する。
- Tailscale はコンテナで稼働。サブネットルート広告が必要なら `TAILSCALE_EXTRA_ARGS` に `--advertise-routes` を指定。
- 外部公開はルーターのポート転送ではなく、Tailscale 経由を推奨。どうしても公開する場合は Nginx 等のリバースプロキシ + 認証を別途用意。
- Firewall (UFW): 既定の OMV/SMB/NFS/SSH に加え、サービス用ポートも開放すること。
  - Jellyfin: `8096`, `8920`
  - Komga: `25600`
  - Stash: `9999` (内部ネットワークのみ推奨、Tailscale経由でのアクセスが望ましい)
  - 設定箇所: `ansible/group_vars/all.yml` の `ufw_allow_ports`

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
- Jellyfin (家族共有動画): `http://raspi-media:8096`
  - iOS 公式アプリからも同URLを指定で接続可
- Komga (家族共有漫画): `http://raspi-media:25600`
  - Web UI: `http://raspi-media:25600`
  - OPDS: `http://raspi-media:25600/opds`
- Stash (個人用メディア): `http://raspi-media:9999`
  - 認証必須、Tailscale経由での利用を推奨
- MagicDNS を使わない場合は `raspi-media` を Tailscale の 100.x.x.x アドレスに置き換えてください。

### ローカルSMBアクセス（OMV 標準）
Windows エクスプローラー:
  - 共有 `media`: `\\\\<固定IP>\\media`（認証必須）
  - 共有 `utatane`: `\\\\<固定IP>\\utatane`（認証必須）
macOS Finder:
  - `smb://<固定IP>/media`（認証必須）, `smb://<固定IP>/utatane`（認証必須）

## セットアップ手順
1. **Raspberry Pi OS 事前準備**
   - Raspberry Pi OS Lite (64-bit, Debian 12 Bookworm ベース) をクリーンインストールし、初期設定で **pi とは別の管理ユーザー** を手動作成して SSH を有効化する。
   - 手動で作成した管理ユーザーで SSH 接続し、`whoami` が期待どおりになっていることと `sudo` が利用できることを確認する（Playbook はこのユーザーで実行する）。
   - UID/GID の数値は気にしなくてよい。Playbook 実行時に自動的に 1000/1000 に揃え、ホーム配下の所有権も修正する。
   - ブートストラップ Playbook (`ansible/playbooks/raspi_bootstrap.yml`) は OpenMediaVault（OMV）本体と `omv-extras` の導入まで自動化する。既に OMV を導入済み、または自分で管理したい場合は `ansible/group_vars/all.yml` の `install_omv` を `false` にするか、実行時に `-e install_omv=false` を付けてスキップする。
   - Playbook 側で installScript の自動リブートを抑止し、Ansible の `reboot` モジュールで再起動と再接続を待つ。再起動後は自動で Play が再開するが、手元の SSH セッションが切れた場合に備えて別途ログイン手段を確保しておくこと。
   - OMV 導入直後でも WebUI 初期設定（管理者パスワード変更、ネットワーク設定、共有フォルダ作成など）は手動で行う必要がある。
   - USB3.0 ストレージを接続し、`ストレージ > ファイルシステム` から EXT4 で初期化のうえマウント。
   - マウント後に `ls -al /srv` や `blkid` で実ディスクの UUID (`/srv/dev-disk-by-uuid-XXXX`) を確認し、後段の `.env` と `ansible/group_vars/all.yml` の `MEDIA_ROOT` 系変数へ反映できるよう控えておく。UUID が未確定のままだと Playbook が失敗する。
   - `アクセス権管理 > 共有フォルダ` で `media` (例: `/srv/dev-disk-by-uuid-XXXX/media`) と `utatane` (例: `/srv/dev-disk-by-uuid-XXXX/utatane`) を作成し、手動で作成した管理ユーザーに必要な権限（読取/必要なら書込）を付与する。

2. **リポジトリ配置**
   - `git clone` もしくは本ディレクトリを OMV ホスト上の任意パスへ配置。
   - `.env` は Ansible テンプレート (`ansible/templates/dotenv.j2`) から生成します。先に `ansible/group_vars/all.yml` の `dotenv` 値を環境に合わせて編集してください。
   - 初期生成や変更反映は Playbook の `dotenv` タグで実施します。
    ```bash
    ansible-playbook -i ansible/inventory.yml ansible/playbooks/raspi_bootstrap.yml --tags dotenv
    ```
    Playbook 全体を実行する場合はタグ指定なしでも `.env` が同時に配置されます。

### Ansible による Raspberry Pi ブートストラップ
- Playbook: `ansible/playbooks/raspi_bootstrap.yml`
  - APT の更新、タイムゾーン/ホスト名設定、`pi` ユーザーの削除、SSH Hardening、UFW/Fail2ban 導入、unattended-upgrades（セキュリティリポジトリのみ自動適用、OMV/カーネル/ブートローダーはブラックリスト）の設定、OMV 未導入時の installScript 実行と `omv-extras` 導入、必要に応じた再起動までを自動化します。
  - `pi` ユーザー削除後に、**手動で作成した管理ユーザーの UID/GID を 1000/1000 に自動で揃え、ホームディレクトリ配下の所有権も調整**します。1000 が別ユーザーで占有されている場合は Playbook が fail するので、先に手動で整理してください。
  - **必ず手動で作成した管理ユーザーで SSH 接続して実行してください。`pi` ユーザーで実行すると Playbook の途中で接続が切れます。**
  - `community.general` コレクション（`ansible-galaxy collection install community.general`）を事前に導入しておくこと。
  - セキュリティリポジトリのみ無人適用し、それ以外（OMV、カーネル、ブートローダー等）はブラックリストで除外しています。機能アップデートは `sudo apt update && sudo apt upgrade --with-new-pkgs` を手動で実行し、適用前に changelog を確認してください。
- インベントリ例（本リポには YAML 例 `ansible/inventory.yml` を同梱）:
  ```yaml
  all:
    children:
      raspi:
        hosts:
          raspi-media:
            ansible_host: 192.168.1.10
            ansible_user: mediaadmin
            ansible_python_interpreter: /usr/bin/python3
  ```
- 実行例:
  ```bash
  export RASPI_TARGET_HOSTS=raspi
  export RASPI_SET_HOSTNAME=raspi-media
  ansible-playbook -i ansible/inventory.yml ansible/playbooks/raspi_bootstrap.yml
  ```
  - `--check` や `--diff` オプションを活用し、変更内容を必ず確認してください。
  - Playbook 実行前に手動作成した管理ユーザーで新たに SSH セッションを貼り直し、`whoami` が期待どおりであることを確認したうえで実行してください。

### OMV 設定用 Playbook
- Playbook: `ansible/playbooks/omv_config.yml`
  - OMV-Extras 経由で Docker を有効化し、Python Docker SDK (`python3-docker`) をインストールします。
  - `.env` と `docker-compose.yml` を前提に、ホスト側ディレクトリ（`CONFIG_ROOT` / `CACHE_ROOT`）を作成し、Jellyfin / Komga / Stash / Tailscale を `docker compose` で起動します。
  - `community.docker` コレクション（`ansible-galaxy collection install community.docker`）が必要です。`community.general` と合わせて事前に導入してください。
  - 実行前に `raspi_bootstrap.yml` が完了していることを前提としています。OMV 未導入または `.env` 未生成の場合は明示的に fail します。

3. **Ansible Playbook 実行（推奨順）**
   - `raspi_bootstrap.yml` で OS 側の初期設定と OMV 導入まで完了させる。
     ```bash
     export RASPI_TARGET_HOSTS=raspi
     export RASPI_SET_HOSTNAME=raspi-media
     ansible-playbook -i ansible/inventory.yml ansible/playbooks/raspi_bootstrap.yml
     ```
   - `raspi_post_omv.yml` を実行し、管理ユーザー整備・.env 生成・OMV-Extras を適用。
     ```bash
     ansible-playbook -i ansible/inventory.yml ansible/playbooks/raspi_post_omv.yml
     ```
   - （暫定）OMV WebUI で共有フォルダを作成し、実パスを `.env` の MEDIA_* に反映。
     - 後日 `omv_storage.yml` を追加し自動化予定。
   - `omv_config.yml` で Docker エンジン導入とコンテナ起動を自動化する。
     ```bash
     export RASPI_TARGET_HOSTS=raspi
     ansible-playbook -i ansible/inventory.yml ansible/playbooks/omv_config.yml
     ```
   - 以後は（任意で）`services_config.yml` による Jellyfin/Komga/Stash の初期設定自動化を順次拡張予定。

4. **動作確認と調整**
   - Jellyfin: WebUI `http://<固定IP>:8096` へアクセスし、ライブラリ「Videos」を `/media/video` に紐付ける（家族共有用）。
   - Komga: WebUI `http://<固定IP>:25600` でライブラリ「Manga」を `/media/books` に作成（家族共有用）。
   - Stash: WebUI `http://<固定IP>:9999` へアクセスし、初期設定ウィザードを完了。ライブラリを `/data` 配下（utatane全体がマウントされている）に設定。認証を必ず有効化する。
   - SMB 共有（OMV 標準）: Windows `\\<固定IP>\<共有名>` / macOS `smb://<固定IP>/<共有名>` でアクセスできるか確認し、必要に応じて OMV 側 ACL を調整。
   - Tailscale: `TAILSCALE_AUTHKEY` を事前投入していない場合は `docker compose exec tailscale tailscale up` でログインし、MagicDNS を有効化して `http://raspi-media:25600` のように名前解決できるか確認する。
   - Tailscale 管理画面でノード登録とサブネット設定を確認。

## ディレクトリ構成 (推奨)
```
/opt/docker
  ├─ jellyfin/config      # Jellyfin 設定・メタデータ
  ├─ jellyfin/cache       # Jellyfin キャッシュ
  ├─ komga/config         # Komga 設定・データベース
  ├─ stash/config         # Stash 設定
  ├─ stash/generated      # Stash サムネイル・生成ファイル
  ├─ stash/metadata       # Stash メタデータ
  ├─ stash/cache          # Stash キャッシュ
  └─ tailscale/state      # Tailscale 状態ファイル

/srv/dev-disk-by-uuid-XXXX/media
  ├─ video/               # 共有(家族)動画 (Jellyfin: /media/video, SMB: \\media\video)
  ├─ picture/             # 共有(家族)写真 (SMB: \\media\picture)
  └─ manga/               # 共有(家族)漫画 (Komga: /media/books, SMB: \\media\manga)

/srv/dev-disk-by-uuid-XXXX/utatane
  ├─ video/               # 個人用動画 (Stash: /data/video, SMB: \\utatane\video)
  ├─ picture/             # 個人用写真 (Stash: /data/picture, SMB: \\utatane\picture)
  └─ manga/               # 個人用漫画 (Stash: /data/manga, SMB: \\utatane\manga)
```
実際の UUID は必ず自分の環境で取得して設定してください。手順は下記「UUID の取得と設定」を参照。設定は `ansible/group_vars/all.yml` の `storage_uuid` だけを更新し、`.env` は Playbook で再生成します（手動編集はしない）。

### UUID の取得と設定（必須）
1. OMV で対象ディスクをファイルシステムとして作成し、マウント済みであることを確認
   - GUI: Storage → File Systems で該当行が Mounted 状態になっていること
2. UUID の確認
   - 簡易: `ls -al /srv` で `dev-disk-by-uuid-XXXXXXXX...` の実パス（マウントディレクトリ）を確認
   - 参考: `sudo blkid` でブロックデバイスの UUID 一覧を確認
   - OMV 設定DB: `sudo omv-confdbadm read conf.system.filesystem.mountpoint | jq -r '.[].dir'`
3. 設定ファイルを更新
   - `ansible/group_vars/all.yml` の `storage_uuid` に取得した UUID を設定（例: `storage_uuid: "6a60..."`）
   - `storage_mount_root` と `.env` の `MEDIA_ROOT` などはこの値から自動導出されます
4. `.env` を再生成
   - `ansible-playbook -i ansible/inventory.yml ansible/playbooks/raspi_post_omv.yml --tags dotenv`
5. 検証
   - リモートで `ls -d /srv/dev-disk-by-uuid-*` が実在し、`.env` の `MEDIA_ROOT` などがその配下を指していること

## Playbook 構成（概要）
- `ansible/playbooks/raspi_bootstrap.yml`: 初期セットアップと OMV 導入（SSH 再接続考慮）
- `ansible/playbooks/raspi_post_omv.yml`: 管理ユーザー整備、.env 生成、OMV-Extras 導入
- `ansible/playbooks/omv_storage.yml`: ディスク/FS/マウントの存在を確認し、README のレイアウトに沿ったディレクトリを作成
- `ansible/playbooks/omv_config.yml`: OMV の共有フォルダ作成と SMB 共有設定（media/utatane）
- `ansible/playbooks/services_deploy.yml`: Docker エンジン導入、必要ディレクトリ作成、Compose 展開（Jellyfin/Komga/Stash/Tailscale）と最小限のサービス設定
- `ansible/playbooks/services_config.yml`: 各サービスの初期設定（追加自動化）
- `ansible/playbooks/main.yml`: 実行順の統括（現状は post_omv → omv_config の順。今後 storage を間に挿入）

## 運用ノート
- Jellyfin のハードウェアトランスコードは Pi では負荷が高いため、基本はソフトウェア再生を想定。解像度やビットレートを事前変換しておくと安定。
- Komga のメタデータはライブラリで指定したパス（例: `/media/books`）以下の構造に依拠するため、命名規則を定めておく。
- Stash はメディアファイルのタグ付け、スタジオ、パフォーマー、シーン管理が可能。初期スキャン後にメタデータを整理すると検索性が向上。認証設定は必須。
- 定期的に `docker compose pull` → `docker compose up -d` で更新。アップデート前に `docker compose logs` でエラーが無いか確認。
- バックアップは `CONFIG_ROOT` 配下とメディアストレージを別ドライブへ同期。最低でも設定ディレクトリは週次バックアップ推奨。特に Stash の設定・メタデータは定期バックアップ推奨。

## OMV での SMB 共有作成（推奨運用）
- 共有フォルダを作成（アクセス方針）
  - media → 実体 `/srv/.../media`（認証必須、家族全員に読取/必要なら書込。配下に video/picture/manga）
  - utatane → 実体 `/srv/.../utatane`（認証必須、許可ユーザーのみ。配下に video/picture/manga）
- 権限/ACL（OMV GUI: アクセス権管理 → 共有フォルダ → 権限/ACL）
  - Jellyfin/Komga/Stash 実行ユーザー（UID/GID=1000）に少なくとも読取付与
    - Jellyfin: media/video のみ
    - Komga: media/manga のみ
    - Stash: utatane 全体に読取/書込
  - utatane は対象ユーザー（または専用グループ）のみに読取/書込権限を付与し、ゲストは拒否
  - LAN 限定にする場合は共有の「追加オプション」に以下例を指定
    - hosts allow = 192.168.0.0/16 10.0.0.0/8
    - hosts deny = 0.0.0.0/0

## ネクストステップ案
- 監視: Netdata や Prometheus Node Exporter を追加して温度/負荷を可視化。
- リバースプロキシ: Nginx Proxy Manager を追加し、HTTPS 経由でのアクセスに統一。
- 外部公開方針が固まり次第、ファイアウォールルールや Fail2ban をホスト側で設定。
