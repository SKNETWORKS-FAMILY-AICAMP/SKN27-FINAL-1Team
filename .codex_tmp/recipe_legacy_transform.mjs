import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const sourcePath = path.resolve("storage/processed/recipe/recipe_final.xlsx");
const outputDir = path.resolve("outputs/recipe-legacy-format");
const outputPath = path.join(outputDir, "recipe_final.xlsx");

const sourceWorkbook = await SpreadsheetFile.importXlsx(await FileBlob.load(sourcePath));
const sourceSheet = sourceWorkbook.worksheets.getItemAt(0);
const sourceRows = sourceSheet.getUsedRange().values;
const sourceHeaders = sourceRows[0];
const sourceData = sourceRows.slice(1);

const sourceIndex = (name) => {
  const index = sourceHeaders.indexOf(name);
  if (index < 0) throw new Error(`컬럼을 찾지 못했습니다: ${name}`);
  return index;
};

const indexes = Object.fromEntries([
  "레시피ID",
  "레시피명",
  "메뉴 대분류",
  "세부 카테고리",
  "주재료",
  "상황 태그",
  "재료명",
  "재료 분량",
  "총 소요 시간(분)",
  "난이도",
].map((name) => [name, sourceIndex(name)]));

const legacyHeaders = [
  "RCP_SNO",
  "CKG_NM",
  "INQ_CNT",
  "SRAP_CNT",
  "CKG_MTH_ACTO_NM",
  "CKG_STA_ACTO_NM",
  "CKG_MTRL_ACTO_NM",
  "CKG_KND_ACTO_NM",
  "CKG_MTRL_CN",
  "CKG_INBUN_NM",
  "CKG_DODF_NM",
  "CKG_TIME_NM",
];

const pythonQuote = (value) => `'${String(value ?? "").replace(/\\/g, "\\\\").replace(/'/g, "\\'")}'`;
const amountPattern = /^(\d+(?:\.\d+)?(?:\/\d+)?|\d+\/\d+)\s*(.*)$/;

function buildIngredientLiteral(namesValue, amountsValue, recipeId) {
  const names = String(namesValue ?? "").split("|").map((value) => value.trim());
  const amounts = String(amountsValue ?? "").split("|").map((value) => value.trim());
  if (names.length !== amounts.length) {
    throw new Error(`재료명과 분량 개수가 다릅니다: ${recipeId} (${names.length}/${amounts.length})`);
  }
  const triples = names.map((name, index) => {
    const amount = amounts[index];
    const match = amount.match(amountPattern);
    const quantity = match ? match[1] : "";
    const unit = match ? match[2] : amount;
    return `[${pythonQuote(name)}, ${pythonQuote(quantity)}, ${pythonQuote(unit)}]`;
  });
  return `[${triples.join(", ")}]`;
}

function legacyDifficulty(value) {
  if (value === "매우 쉬움" || value === "쉬움") return "초급";
  if (value === "보통") return "중급";
  return "고급";
}

const legacyRows = sourceData.map((row) => {
  const recipeId = Number(row[indexes["레시피ID"]]);
  const minutes = Number(row[indexes["총 소요 시간(분)"]]);
  if (!Number.isInteger(recipeId) || recipeId <= 0) throw new Error(`잘못된 레시피 ID: ${recipeId}`);
  if (!Number.isFinite(minutes) || minutes <= 0) throw new Error(`잘못된 소요 시간: ${recipeId}`);
  return [
    recipeId,
    String(row[indexes["레시피명"]] ?? "").trim(),
    0,
    0,
    String(row[indexes["세부 카테고리"]] ?? "").trim(),
    String(row[indexes["상황 태그"]] ?? "").trim(),
    String(row[indexes["주재료"]] ?? "").trim(),
    String(row[indexes["메뉴 대분류"]] ?? "").trim(),
    buildIngredientLiteral(
      row[indexes["재료명"]],
      row[indexes["재료 분량"]],
      recipeId,
    ),
    "1인분",
    legacyDifficulty(String(row[indexes["난이도"]] ?? "").trim()),
    `${minutes}분이내`,
  ];
});

if (legacyRows.length !== 171) throw new Error(`예상과 다른 레시피 행 수: ${legacyRows.length}`);
if (new Set(legacyRows.map((row) => row[0])).size !== legacyRows.length) {
  throw new Error("RCP_SNO 중복이 있습니다.");
}

const workbook = Workbook.create();
const legacySheet = workbook.worksheets.add("recipe_final");
const detailSheet = workbook.worksheets.add("recipe_detail");

legacySheet.getRangeByIndexes(0, 0, legacyRows.length + 1, legacyHeaders.length).values = [
  legacyHeaders,
  ...legacyRows,
];
detailSheet.getRangeByIndexes(0, 0, sourceRows.length, sourceHeaders.length).values = sourceRows;

legacySheet.tables.add(`A1:L${legacyRows.length + 1}`, true, "RecipeFinalTable");
detailSheet.tables.add(`A1:W${sourceRows.length}`, true, "RecipeDetailTable");

for (const sheet of [legacySheet, detailSheet]) {
  sheet.freezePanes.freezeRows(1);
  sheet.showGridLines = false;
}

legacySheet.getRange("A1:L1").format = {
  fill: "#FBEAEC",
  font: { bold: true, color: "#4A2626" },
  rowHeight: 26,
};
legacySheet.getRange(`A2:L${legacyRows.length + 1}`).format.rowHeight = 22;
legacySheet.getRange(`A2:D${legacyRows.length + 1}`).format.horizontalAlignment = "right";
legacySheet.getRange(`A2:L${legacyRows.length + 1}`).format.verticalAlignment = "center";
legacySheet.getRange("A:A").format.columnWidth = 12;
legacySheet.getRange("B:B").format.columnWidth = 24;
legacySheet.getRange("C:D").format.columnWidth = 10;
legacySheet.getRange("E:E").format.columnWidth = 20;
legacySheet.getRange("F:F").format.columnWidth = 34;
legacySheet.getRange("G:H").format.columnWidth = 22;
legacySheet.getRange("I:I").format.columnWidth = 72;
legacySheet.getRange("J:L").format.columnWidth = 14;

detailSheet.getRange("A1:W1").format = {
  fill: "#F7F3EE",
  font: { bold: true, color: "#3F3028" },
  rowHeight: 26,
};
detailSheet.getRange(`A2:W${sourceRows.length}`).format.rowHeight = 22;

const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log("FORMULA_ERRORS", formulaErrors.ndjson);
console.log("PREVIEW", (await workbook.inspect({
  kind: "table",
  sheetId: legacySheet.name,
  range: "A1:L6",
  include: "values,formulas",
  tableMaxRows: 6,
  tableMaxCols: 12,
  tableMaxCellChars: 200,
  maxChars: 12000,
})).ndjson);

await fs.mkdir(outputDir, { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

const verifyWorkbook = await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
const verifyLegacy = verifyWorkbook.worksheets.getItem("recipe_final").getUsedRange().values;
const verifyDetail = verifyWorkbook.worksheets.getItem("recipe_detail").getUsedRange().values;
if (verifyLegacy.length !== 172 || verifyLegacy[0].length !== 12) {
  throw new Error("recipe_final 시트 크기 검증에 실패했습니다.");
}
if (verifyDetail.length !== 172 || verifyDetail[0].length !== 23) {
  throw new Error("recipe_detail 시트 보존 검증에 실패했습니다.");
}
if (JSON.stringify(verifyLegacy[0]) !== JSON.stringify(legacyHeaders)) {
  throw new Error("legacy 헤더 검증에 실패했습니다.");
}

const sourceOutput = await SpreadsheetFile.exportXlsx(verifyWorkbook);
await sourceOutput.save(sourcePath);

console.log("OUTPUT", outputPath);
console.log("LEGACY_ROWS", verifyLegacy.length - 1);
console.log("DETAIL_ROWS", verifyDetail.length - 1);
