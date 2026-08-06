import fs from "node:fs/promises";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

const outDir = "outputs/canadian-personal-data-removal";
await fs.mkdir(outDir, { recursive: true });
const wb = Workbook.create();
const ws = wb.worksheets.add("Removal Tracker");
ws.showGridLines = false;
ws.getRange("A1:N1").merge();
ws.getRange("A1").values = [["PRIVATE — Personal Data Removal Tracker"]];
ws.getRange("A1:N1").format = {fill:"#1F4E78",font:{bold:true,color:"#FFFFFF",size:16},horizontalAlignment:"center",verticalAlignment:"center"};
ws.getRange("A2:N2").merge();
ws.getRange("A2").values = [["Do not store SIN, passwords, full ID images, or unnecessary birth/address details here. Keep CAPTCHA, login, verification links, ID upload, and final submission manual."]];
ws.getRange("A2:N2").format = {fill:"#FFF2CC",font:{color:"#7A5A00",italic:true},wrapText:true};
const headers = ["Website","Listing URL","Information Exposed","Risk","Official Opt-Out URL","Jurisdiction","Recommended Action","Status","Date Checked","Date Submitted","Response Due","Confirmation / Case ID","Next Recheck","Notes"];
ws.getRange("A4:N4").values = [headers];
ws.getRange("A4:N4").format = {fill:"#D9EAF7",font:{bold:true,color:"#17365D"},wrapText:true,borders:{preset:"all",style:"thin",color:"#AAB7C4"},verticalAlignment:"center"};
const rows = Array.from({length:100},()=>Array(14).fill(""));
ws.getRange("A5:N104").values = rows;
ws.getRange("A5:N104").format = {borders:{preset:"all",style:"thin",color:"#D9E1E8"},verticalAlignment:"top",wrapText:true};
ws.getRange("D5:D104").dataValidation = {rule:{type:"list",values:["High","Medium","Low"]}};
ws.getRange("H5:H104").dataValidation = {rule:{type:"list",values:["Discovered","Review Needed","Ready to Submit","Submitted","Awaiting Response","Removed / Suppressed","Corrected","Denied","Manual Verification","Reappeared","Not Removable"]}};
ws.getRange("I5:K104").format.numberFormat = "yyyy-mm-dd";
ws.getRange("M5:M104").format.numberFormat = "yyyy-mm-dd";
ws.getRange("D5:D104").conditionalFormats.add("containsText",{text:"High",format:{fill:"#F4CCCC",font:{color:"#9C0006",bold:true}}});
ws.getRange("D5:D104").conditionalFormats.add("containsText",{text:"Medium",format:{fill:"#FFF2CC",font:{color:"#7F6000"}}});
ws.getRange("D5:D104").conditionalFormats.add("containsText",{text:"Low",format:{fill:"#D9EAD3",font:{color:"#274E13"}}});
ws.freezePanes.freezeRows(4);
const widths = [18,30,28,11,30,18,30,22,13,13,13,20,13,34];
for (let i=0;i<14;i++) ws.getRangeByIndexes(0,i,104,1).format.columnWidth = widths[i];
ws.getRange("1:1").format.rowHeight = 28;
ws.getRange("2:2").format.rowHeight = 38;
ws.getRange("4:4").format.rowHeight = 34;
const table = ws.tables.add("A4:N104", true, "RemovalTracker");
table.style = "TableStyleMedium2";

const lists = wb.worksheets.add("Instructions");
lists.showGridLines = false;
lists.getRange("A1:F1").merge();
lists.getRange("A1").values = [["How to use this tracker"]];
lists.getRange("A1:F1").format = {fill:"#1F4E78",font:{bold:true,color:"#FFFFFF",size:16}};
const content = [
["Step","Action"],
["1","Record a result without copying more personal data than necessary."],
["2","Confirm the listing is yours; score the risk; locate the official privacy/opt-out page."],
["3","Tailor the request to the site and jurisdiction. Do not assume PIPEDA or a foreign law applies."],
["4","Complete CAPTCHA, login, identity upload, verification link, and final submission yourself."],
["5","Record the confirmation and response target. PIPEDA access requests generally use a 30-calendar-day response period, subject to permitted extensions."],
["6","Recheck the direct URL and minimum original search. Record reappearance as a new event."],
["Risk","High: address, phone, birth date, relatives, or combined identifiers. Medium: personal email, employment history, detailed profile. Low: ordinary professional/public reference."],
["Privacy","Keep the workbook on a trusted local device. Do not put SIN, passwords, ID images, or unnecessary identity details in it."],
];
lists.getRange("A3:B11").values = content;
lists.getRange("A3:B3").format = {fill:"#D9EAF7",font:{bold:true,color:"#17365D"},borders:{preset:"all",style:"thin",color:"#AAB7C4"}};
lists.getRange("A4:B11").format = {wrapText:true,verticalAlignment:"top",borders:{preset:"all",style:"thin",color:"#D9E1E8"}};
lists.getRange("A:A").format.columnWidth = 14;
lists.getRange("B:B").format.columnWidth = 95;
lists.getRange("A3:B11").format.autofitRows();
lists.freezePanes.freezeRows(3);

const inspect = await wb.inspect({kind:"table",sheetId:"Removal Tracker",range:"A1:N10",include:"values,formulas",tableMaxRows:10,tableMaxCols:14,maxChars:5000});
console.log(inspect.ndjson);
const errors = await wb.inspect({kind:"match",searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",options:{useRegex:true,maxResults:100},summary:"formula error scan"});
console.log(errors.ndjson);
const preview1 = await wb.render({sheetName:"Removal Tracker",range:"A1:N18",scale:1,format:"png"});
await fs.writeFile(`${outDir}/tracker-preview.png`,new Uint8Array(await preview1.arrayBuffer()));
const preview2 = await wb.render({sheetName:"Instructions",range:"A1:B11",scale:1,format:"png"});
await fs.writeFile(`${outDir}/instructions-preview.png`,new Uint8Array(await preview2.arrayBuffer()));
const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(`${outDir}/Personal_Data_Removal_Tracker.xlsx`);
console.log(`${outDir}/Personal_Data_Removal_Tracker.xlsx`);
