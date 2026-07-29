const specifier = "https://module.__HARNESS_DOMAIN__/ev026-__RUN_TAG__.ts";

await import(specifier);
throw new Error("EV026_DYNAMIC_IMPORT_MODEL_BODY_EXECUTED");
