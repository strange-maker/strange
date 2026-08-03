import { access, copyFile, cp, mkdir, rm } from "node:fs/promises";
import { resolve } from "node:path";
import type { Plugin } from "vite";

async function exists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return false;
    }
    throw error;
  }
}

// Packages Sites metadata and migrations after Vite finishes compiling.
export function sites(): Plugin {
  let root = process.cwd();
  let packageOutput = Promise.resolve();

  return {
    name: "sites",
    apply: "build",
    configResolved(config) {
      root = config.root;
    },
    async closeBundle() {
      // Vite/RSC can invoke closeBundle for multiple environments at once.
      // Serialize packaging so one environment cannot remove `.openai` while
      // another environment is still copying hosting.json into it.
      packageOutput = packageOutput.then(async () => {
        const outputDirectory = resolve(root, "dist", ".openai");
        const hostingConfig = resolve(root, ".openai", "hosting.json");
        const drizzleSource = resolve(root, "drizzle");

        await rm(outputDirectory, { recursive: true, force: true });
        await mkdir(outputDirectory, { recursive: true });

        if (await exists(hostingConfig)) {
          await copyFile(hostingConfig, resolve(outputDirectory, "hosting.json"));
        }
        if (await exists(drizzleSource)) {
          await cp(drizzleSource, resolve(outputDirectory, "drizzle"), {
            recursive: true,
          });
        }
      });
      await packageOutput;
    },
  };
}
