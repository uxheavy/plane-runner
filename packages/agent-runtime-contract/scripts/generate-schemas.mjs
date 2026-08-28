import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { access, mkdir, mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import { resolve } from "node:path";
import { tmpdir } from "node:os";

import { protocol as defaultProtocol, schemas as defaultSchemas } from "../src/schema-source.mjs";

const defaultOutputDirectory = fileURLToPath(
  new URL("../../../apps/api/plane/agent/lifecycle/contract_artifacts/v1/", import.meta.url)
);
const defaultLocalFormatterPath = fileURLToPath(new URL("../../../node_modules/.bin/oxfmt", import.meta.url));
const defaultFormatterConfigPath = fileURLToPath(new URL("../../../.oxfmtrc.json", import.meta.url));
export const manifestFilename = "manifest.json";

const canonicalJson = (value) => `${JSON.stringify(value, null, 2)}\n`;
const sha256 = (value) => createHash("sha256").update(value).digest("hex");

const formatFiles = (directory, filenames, formatterPath, formatterConfigPath) => {
  execFileSync(formatterPath, ["--config", formatterConfigPath, "--ignore-path=.prettierignore", ...filenames], {
    cwd: directory,
    stdio: "ignore",
  });
};

export const buildExpectedFiles = async ({
  directory,
  schemas = defaultSchemas,
  protocol = defaultProtocol,
  formatterPath,
  formatterConfigPath = defaultFormatterConfigPath,
}) => {
  const resolvedFormatterPath = formatterPath ?? (await resolveFormatterPath());
  const rawSchemaFiles = new Map(
    Object.entries(schemas).map(([name, schema]) => [`${name}.schema.json`, canonicalJson(schema)])
  );

  await mkdir(directory, { recursive: true });
  await writeFile(`${directory}/.prettierignore`, "", "utf8");
  await Promise.all(
    [...rawSchemaFiles].map(([filename, contents]) => writeFile(`${directory}/${filename}`, contents, "utf8"))
  );
  formatFiles(directory, [...rawSchemaFiles.keys()], resolvedFormatterPath, formatterConfigPath);

  const formattedSchemas = new Map(
    await Promise.all(
      [...rawSchemaFiles.keys()].map(async (filename) => [filename, await readFile(`${directory}/${filename}`, "utf8")])
    )
  );
  const manifest = {
    protocol,
    schemas: Object.fromEntries(
      [...formattedSchemas.entries()].map(([filename, contents]) => [
        filename.replace(".schema.json", ""),
        { filename, sha256: sha256(contents) },
      ])
    ),
  };
  await writeFile(`${directory}/${manifestFilename}`, canonicalJson(manifest), "utf8");
  formatFiles(directory, [manifestFilename], resolvedFormatterPath, formatterConfigPath);

  return new Map([...formattedSchemas, [manifestFilename, await readFile(`${directory}/${manifestFilename}`, "utf8")]]);
};

const resolveFormatterPath = async (formatterPath) => {
  if (formatterPath !== undefined) {
    return formatterPath;
  }

  return access(defaultLocalFormatterPath)
    .then(() => defaultLocalFormatterPath)
    .catch(() => process.env.OXFMT_PATH ?? "oxfmt");
};

export async function generateSchemas({
  schemas = defaultSchemas,
  protocol = defaultProtocol,
  outputDirectory = defaultOutputDirectory,
  checkOnly = false,
  formatterPath,
  formatterConfigPath = defaultFormatterConfigPath,
} = {}) {
  const resolvedFormatterPath = await resolveFormatterPath(formatterPath);
  const temporaryDirectory = await mkdtemp(`${tmpdir()}/plane-agent-runtime-contract-`);

  try {
    const expectedFiles = await buildExpectedFiles({
      directory: temporaryDirectory,
      schemas,
      protocol,
      formatterPath: resolvedFormatterPath,
      formatterConfigPath,
    });
    const filesToCheck = [...expectedFiles.entries()];
    const mismatches = (
      await Promise.all(
        filesToCheck.map(async ([filename, expected]) => {
          try {
            const actual = await readFile(`${outputDirectory}/${filename}`, "utf8");
            return actual === expected ? undefined : filename;
          } catch {
            return filename;
          }
        })
      )
    ).filter((filename) => filename !== undefined);

    if (checkOnly) {
      const actualFiles = await readdir(outputDirectory).catch(() => []);
      const expectedFilenames = new Set(filesToCheck.map(([filename]) => filename));
      for (const filename of actualFiles) {
        if (!expectedFilenames.has(filename)) {
          mismatches.push(filename);
        }
      }
      return { mismatches: [...new Set(mismatches)].toSorted(), files: expectedFiles };
    }

    await mkdir(outputDirectory, { recursive: true });
    await Promise.all(
      filesToCheck.map(([filename, contents]) => writeFile(`${outputDirectory}/${filename}`, contents, "utf8"))
    );
    return { mismatches: [], files: expectedFiles };
  } finally {
    await rm(temporaryDirectory, { recursive: true, force: true });
  }
}

if (process.argv[1] !== undefined && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  const checkOnly = process.argv.includes("--check");
  const result = await generateSchemas({ checkOnly });
  if (checkOnly && result.mismatches.length > 0) {
    console.error(`Generated contract drift detected: ${result.mismatches.join(", ")}`);
    process.exitCode = 1;
  } else if (checkOnly) {
    console.log("Generated contract schemas are up to date.");
  } else {
    console.log(`Generated ${result.files.size} deterministic contract artifacts.`);
  }
}
