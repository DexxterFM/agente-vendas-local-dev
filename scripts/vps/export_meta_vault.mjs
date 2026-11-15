#!/usr/bin/env node
/**
 * Exporta exclusivamente a configuração Meta necessária ao worker para um
 * EnvironmentFile local. Executa sob o usuário dono do cofre AvanthCode e
 * nunca escreve valores em stdout/stderr.
 */
import { createCipheriv, createDecipheriv, createHash } from "node:crypto";
import { chmod, readFile, rename, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join } from "node:path";

const stateRoot = process.env.AVANTHCODE_AGENT_STATE_DIR || "/var/lib/avanthcode-agent";
const configDir = join(stateRoot, "config");
const vaultPath = join(configDir, "secure-config.enc.json");
const outputPath = process.env.SALES_AGENT_META_ENV || join(configDir, "sales-agent-meta.env");
const keyPath = join(configDir, ".master-key");
const allowed = [
  "PAGE_ACCESS_TOKEN",
  "INSTAGRAM_ACCESS_TOKEN",
  "IG_BUSINESS_ACCOUNT_ID",
  "INSTAGRAM_BUSINESS_ACCOUNT_ID",
  "META_LOGIN_MODE",
  "META_GRAPH_VERSION",
];

function envValue(value) {
  // Tokens e IDs não precisam de aspas; rejeite quebras que poderiam criar
  // outra variável no arquivo EnvironmentFile.
  return String(value || "").replace(/[\r\n]/g, "").trim();
}

async function vaultKey() {
  if (process.env.AGENT_CONFIG_ENCRYPTION_KEY) {
    return createHash("sha256").update(process.env.AGENT_CONFIG_ENCRYPTION_KEY).digest();
  }
  if (!existsSync(keyPath)) throw new Error("Chave do cofre indisponível");
  return createHash("sha256").update(await readFile(keyPath)).digest();
}

async function main() {
  if (!existsSync(vaultPath)) throw new Error("Cofre Meta indisponível");
  const envelope = JSON.parse(await readFile(vaultPath, "utf8"));
  const decipher = createDecipheriv("aes-256-gcm", await vaultKey(), Buffer.from(String(envelope.iv || ""), "base64"));
  decipher.setAuthTag(Buffer.from(String(envelope.tag || ""), "base64"));
  const config = JSON.parse(Buffer.concat([
    decipher.update(Buffer.from(String(envelope.data || ""), "base64")),
    decipher.final(),
  ]).toString("utf8"));
  const token = envValue(config.INSTAGRAM_ACCESS_TOKEN || config.PAGE_ACCESS_TOKEN);
  const account = envValue(config.IG_BUSINESS_ACCOUNT_ID || config.INSTAGRAM_BUSINESS_ACCOUNT_ID);
  if (!token || !account) throw new Error("Cofre não contém conexão Instagram completa");
  const rows = allowed
    .map((key) => [key, envValue(config[key])])
    .filter(([, value]) => Boolean(value))
    .map(([key, value]) => `${key}=${value}`);
  const temporary = `${outputPath}.${process.pid}.tmp`;
  // PID 1 lê este arquivo para montar o ambiente dos serviços; nenhum outro
  // usuário precisa ter acesso direto ao conteúdo.
  await writeFile(temporary, `${rows.join("\n")}\n`, { encoding: "utf8", mode: 0o600, flag: "w" });
  await rename(temporary, outputPath);
  await chmod(outputPath, 0o600);
  // Saída propositalmente sanitizada para logs do systemd.
  console.log(`Meta vault exported (${rows.length} settings)`);
}

main().catch((error) => {
  console.error(`Meta vault export failed: ${String(error?.message || error).slice(0, 180)}`);
  process.exitCode = 1;
});
