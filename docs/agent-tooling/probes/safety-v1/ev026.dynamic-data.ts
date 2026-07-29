const specifier = "data:text/javascript,export default 1";

await import(specifier);
throw new Error("EV026_DYNAMIC_IMPORT_MODEL_BODY_EXECUTED");
