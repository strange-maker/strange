import { spawnSync } from "node:child_process";

const executable = process.platform === "win32" ? "vinext.cmd" : "vinext";
const result = spawnSync(executable, ["build"], {
  cwd: process.cwd(),
  env: { ...process.env, VINEXT_SITES_BUILD: "1" },
  shell: process.platform === "win32",
  stdio: "inherit",
});

if (result.error) {
  console.error(result.error);
  process.exit(1);
}

process.exit(result.status ?? 1);
