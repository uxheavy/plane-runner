const specifier = "jsr:@std/path@1.1.2";

await import(specifier);
throw new Error("EV026_DYNAMIC_IMPORT_MODEL_BODY_EXECUTED");
