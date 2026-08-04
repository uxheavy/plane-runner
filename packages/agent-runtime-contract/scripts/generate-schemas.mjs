import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { access, mkdir, mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";

import { protocol, schemas } from "../src/schema-source.mjs";

const outputDirectory = fileURLToPath(new URL("../schemas/v1/", import.meta.url));
const localFormatterPath = fileURLToPath(new URL("../../../node_modules/.bin/oxfmt", import.meta.url));
const formatterConfigPath = fileURLToPath(new URL("../../../.oxfmtrc.json", import.meta.url));
const manifestFilename = "manifest.json";
const checkOnly = process.argv.includes("--check");

const formatterPath = await access(localFormatterPath)
  .then(() => localFormatterPath)
  .catch(() => process.env.OXFMT_PATH ?? "oxfmt");

const canonicalJson = (value) => `${JSON.stringify(value, null, 2)}\n`;
const sha256 = (value) => createHash("sha256").update(value).digest("hex");

const rawSchemaFiles = new Map(
  Object.entries(schemas).map(([name, schema]) => [`${name}.schema.json`, canonicalJson(schema)])
);

const formatFiles = (directory, filenames) => {
  execFileSync(formatterPath, ["--config", formatterConfigPath, "--ignore-path=.prettierignore", ...filenames], {
    cwd: directory,
    stdio: "ignore",
  });
};

const buildExpectedFiles = async (directory) => {
  await mkdir(directory, { recursive: true });
  await writeFile(`${directory}/.prettierignore`, "", "utf8");
  await Promise.all(
    [...rawSchemaFiles].map(([filename, contents]) => writeFile(`${directory}/${filename}`, contents, "utf8"))
  );
  formatFiles(directory, [...rawSchemaFiles.keys()]);

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
  formatFiles(directory, [manifestFilename]);

  return new Map([...formattedSchemas, [manifestFilename, await readFile(`${directory}/${manifestFilename}`, "utf8")]]);
};

const temporaryDirectory = await mkdtemp(`${tmpdir()}/plane-agent-runtime-contract-`);
try {
  const expectedFiles = await buildExpectedFiles(temporaryDirectory);
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

    if (mismatches.length > 0) {
      console.error(`Generated contract drift detected: ${[...new Set(mismatches)].toSorted().join(", ")}`);
      process.exitCode = 1;
    } else {
      console.log("Generated contract schemas are up to date.");
    }
  } else {
    await mkdir(outputDirectory, { recursive: true });
    await Promise.all(
      filesToCheck.map(([filename, contents]) => writeFile(`${outputDirectory}/${filename}`, contents, "utf8"))
    );
    console.log(`Generated ${filesToCheck.length} deterministic contract artifacts.`);
  }
} finally {
  await rm(temporaryDirectory, { recursive: true, force: true });
}
