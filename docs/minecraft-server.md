# Minecraft (Bedrock) — BedrockConnect + DNS (macvlan)

本ドキュメントは、raspi-media-server 環境に BedrockConnect と DNS リダイレクト（dnsmasq）を macvlan で独立させて追加する設計・実装計画です。ホストのポートやUFWには一切触れず、L2 直結の独立IPで待受します。

- 目的: 家庭内LAN上で BedrockConnect を安定稼働させ、端末の DNS を本機に向けるだけで Bedrock のサーバー選択画面を実現
- 方式: macvlan ネットワーク上で `dnsmasq` と `bedrockconnect` を固定IPで運用
- 非目標: ホスト側の 53/19132 ポート占有、Firewall 設定変更、bridge 共有
- 前提: 端末/ルーター側で DNS を `dnsmasq` のIPに設定（DHCP配布または手動）

---

## 最終方針（確定）
- ネットワーク: macvlan ネットワーク `lan_net` を作成し、親IF直下に直結
- IP割当: `dnsmasq` と `bedrockconnect` に固定IPを各1つ割当
- ポート公開: なし（macvlan上で各サービスがネイティブに 53/udp,tcp / 19132/udp を待受）
- 既存サービス: 既存は `media_net`（bridge）、Tailscale は `host` のまま分離
- 競合回避: ホストの 53 番を使わず、UFW も変更しない

---

## 変数（.env / group_vars）
下記を `.env` と `ansible/group_vars/all.yml` の `dotenv` に追加します。

- `LAN_PARENT_IF`（例: `eth0`）
- `LAN_SUBNET`（例: `192.168.1.0/24`）
- `LAN_GATEWAY`（例: `192.168.1.1`）
- `DNSMASQ_IP`（例: `192.168.1.253`）
- `BEDROCKCONNECT_IP`（例: `192.168.1.252`）
- `DNSMASQ_FORWARD`（例: `1.1.1.1,1.0.0.1`）
- `DNSMASQ_OVERRIDE_DOMAINS`（例: `friends.minecraft.net`）
- （任意）`DNSMASQ_IMAGE`（例: `andyshinn/dnsmasq:2.87`）
- （任意）`BEDROCKCONNECT_IMAGE`（要確認・決定。後述）

注意:
- 固定IPは必ずDHCPプールの外に置く（例: 配布範囲 100–199 の場合、.252/.253 は安全側）
- 親IF名は実機のIF名（OMV環境で `eth0` とは限らない）
- macvlan 配下はホスト(Raspi)から直接疎通できない（検証は別端末から）

---

## docker-compose の設計

macvlan ネットワークを追加し、`dnsmasq` と `bedrockconnect` を固定IPで参加させます。ポート公開は不要です。

```yaml
networks:
  lan_net:
    driver: macvlan
    driver_opts:
      parent: ${LAN_PARENT_IF}
    ipam:
      config:
        - subnet: ${LAN_SUBNET}
          gateway: ${LAN_GATEWAY}
```

サービス例（イメージは例示。実採用時に固定化してタグ管理すること）:

```yaml
services:
  dnsq:
    image: ${DNSMASQ_IMAGE:-andyshinn/dnsmasq:2.87}
    container_name: dnsq
    restart: unless-stopped
    # ポート公開なし（macvlanでネイティブ待受）
    volumes:
      - ${CONFIG_ROOT:-/opt/docker}/dnsmasq/dnsmasq.conf:/etc/dnsmasq.conf:ro
      - ${CONFIG_ROOT:-/opt/docker}/dnsmasq/conf.d:/etc/dnsmasq.d:ro
    networks:
      lan_net:
        ipv4_address: ${DNSMASQ_IP}

  bedrockconnect:
    image: ${BEDROCKCONNECT_IMAGE}  # 要: 使用する公式/信頼イメージ名を決定
    container_name: bedrockconnect
    restart: unless-stopped
    # ポート公開なし（macvlanで 19132/udp をネイティブ待受）
    networks:
      lan_net:
        ipv4_address: ${BEDROCKCONNECT_IP}
```

メモ:
- `andyshinn/dnsmasq` は軽量で用途に十分。GUI不要なら十分実用
- BedrockConnect の公式/信頼イメージ名は採用前に確認・固定（タグピン止め）

---

## dnsmasq 設定（テンプレート）
Ansible で `${CONFIG_ROOT}/dnsmasq` 配下に出力します。

- `dnsmasq.conf`
  - `no-resolv`（OSの `/etc/resolv.conf` は使わない）
  - `server=<上流DNS>`（`,`区切りを展開）
  - `domain-needed`, `bogus-priv`（ローカル誤解決を抑制）
  - `cache-size=10000`（適度なキャッシュ）
  - `conf-dir=/etc/dnsmasq.d,*.conf`

- `conf.d/bedrockconnect.conf`
  - `DNSMASQ_OVERRIDE_DOMAINS` をカンマ区切りで展開し、各FQDNを `BEDROCKCONNECT_IP` に上書き
  - 例: `address=/friends.minecraft.net/192.168.1.252`

---

## Ansible 拡張（実装方針）
既存の `roles/docker_services` と `roles/services_config` を活用し、最小変更で組み込みます。

- ディレクトリ作成（`roles/docker_services` 内の「docker関連ディレクトリ作成」に追記）
  - 追加: `${CONFIG_ROOT}/dnsmasq`, `${CONFIG_ROOT}/dnsmasq/conf.d`, `${CONFIG_ROOT}/bedrockconnect`

- テンプレート出力（`roles/services_config` で dotenv 読込ロジックを流用）
  - 追加テンプレート:
    - `roles/services_config/templates/dnsmasq.conf.j2`
    - `roles/services_config/templates/dnsmasq-bedrockconnect.conf.j2`
  - 出力先:
    - `${CONFIG_ROOT}/dnsmasq/dnsmasq.conf`
    - `${CONFIG_ROOT}/dnsmasq/conf.d/bedrockconnect.conf`

- Compose 適用
  - 既存の `roles/docker_compose_project` をそのまま利用（`files: docker-compose.yml`）
  - Compose ファイルに `lan_net` と2サービスを追記

- 変数/テンプレートの拡張
  - `ansible/group_vars/all.yml` の `dotenv` に本ドキュメントの変数を追加
  - `roles/dotenv/templates/dotenv.j2` に同名項目を追記

- UFW/ホスト設定
  - macvlan 方針のため変更不要（ポート開放なし、ホスト53番とは無関係）

---

## 反映手順（運用）
1) 値を確定・設定
- `.env` 及び `ansible/group_vars/all.yml` の `dotenv` に以下を設定
  - `LAN_PARENT_IF`, `LAN_SUBNET`, `LAN_GATEWAY`
  - `DNSMASQ_IP`, `BEDROCKCONNECT_IP`
  - `DNSMASQ_FORWARD`, `DNSMASQ_OVERRIDE_DOMAINS`
  - 必要なら `DNSMASQ_IMAGE`, `BEDROCKCONNECT_IMAGE`

2) テンプレート/Compose 追加（Ansible 実装後）
- `ansible-playbook -i ansible/inventory.yml ansible/playbooks/services_deploy.yml`

3) ルーター/DHCP 設定
- DHCP の DNS 配布先を `DNSMASQ_IP` に変更、または端末で手動指定

4) 動作確認（必ず別端末から）
- `nslookup friends.minecraft.net DNSMASQ_IP` で `BEDROCKCONNECT_IP` を返すこと
- Nintendo Switch/モバイル等の Bedrock クライアントからサーバーリストが出ること

---

## 検証ポイントと注意
- macvlan の性質上、ホストから `DNSMASQ_IP`/`BEDROCKCONNECT_IP` へ直接疎通はできない（仕様）
- DHCP プールと固定IPの重複は不可。重複すると断続的に名前解決不能になる
- 上書きFQDNは最小から始める（推奨: `friends.minecraft.net` のみ）。過剰上書きは副作用の温床
- ルーターの DoH/DoT（DNS over HTTPS/TLS）バイパス設定がある場合、端末から外に逃げる可能性があるため無効化/フィルタを検討

---

## ロールバック
- 端末/DHCP の DNS 指定を元に戻す
- Compose から `dnsq`/`bedrockconnect`/`lan_net` の定義を削除し、`docker compose up -d`
- `${CONFIG_ROOT}/dnsmasq` 等のディレクトリ/テンプレートは残置しても可（再利用想定）

---

## 未決事項（要決定）
- `BEDROCKCONNECT_IMAGE` の公式/信頼イメージ名とタグ（固定すること）
- 実IF名（`LAN_PARENT_IF`）、サブネット、ゲートウェイ
- 固定IP（`DNSMASQ_IP`, `BEDROCKCONNECT_IP`）
- 上流DNS（`DNSMASQ_FORWARD`）と上書きFQDN（`DNSMASQ_OVERRIDE_DOMAINS`）

決まった値を `dotenv` に反映後、Ansible 実装（テンプレートとCompose追記）を適用すれば稼働可能です。
