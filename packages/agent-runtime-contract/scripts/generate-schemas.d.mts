export type SchemaDefinitions = Record<string, unknown>;

export type GenerateSchemasOptions = Readonly<{
  schemas?: SchemaDefinitions;
  protocol?: string;
  outputDirectory?: string;
  checkOnly?: boolean;
  formatterPath?: string;
  formatterConfigPath?: string;
}>;

export type GeneratedSchemaResult = Readonly<{
  mismatches: readonly string[];
  files: ReadonlyMap<string, string>;
}>;

export declare const manifestFilename: string;
export declare function generateSchemas(options?: GenerateSchemasOptions): Promise<GeneratedSchemaResult>;
