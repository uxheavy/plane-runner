const specifier = "file:///etc/passwd";

await import(specifier);
throw new Error("EV026_DYNAMIC_IMPORT_MODEL_BODY_EXECUTED");
