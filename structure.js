function createTimeTrackerSystem() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  
  // === 1. ЛИСТ ЛОГОВ ===
  let sheetLogs = ss.getSheetByName("DB_Logs");
  if (!sheetLogs) {
    sheetLogs = ss.insertSheet("DB_Logs");
  } else {
    sheetLogs.clear();
  }
  
  sheetLogs.getRange("A1:E1").setValues([["Дата", "Время", "ФИО Сотрудника", "Тип (Info)", "Tg_ID"]])
    .setFontWeight("bold");
  sheetLogs.getRange("A:A").setNumberFormat("dd.MM.yyyy");
  sheetLogs.getRange("B:B").setNumberFormat("HH:mm");

  // Тестовые данные
  const dummyLogs = [
    [new Date(2025, 11, 1), "08:55", "Сотрудник 1", "Приход", 12345], 
    [new Date(2025, 11, 1), "18:05", "Сотрудник 1", "Уход", 12345],   
    [new Date(2025, 11, 1), "09:15", "Сотрудник 2", "Приход", 67890], 
    [new Date(2025, 11, 1), "17:55", "Сотрудник 2", "Уход", 67890]    
  ];
  sheetLogs.getRange(2, 1, dummyLogs.length, 5).setValues(dummyLogs);


  // === 2. ЛИСТ ОТЧЕТА ===
  let sheetReport = ss.getSheetByName("Отчет_Декабрь");
  if (!sheetReport) {
    sheetReport = ss.insertSheet("Отчет_Декабрь");
  } else {
    try {
      sheetReport.collapseAllColumnGroups();
      for(let i=0; i<10; i++) {
        let group = sheetReport.getColumnGroup(3, 1);
        if (group) group.remove(); else break;
      }
      for(let i=0; i<10; i++) {
        let group = sheetReport.getColumnGroup(4, 1); 
        if (group) group.remove(); else break;
      }
    } catch(e) {}
    sheetReport.clear();
  }

  const empCount = 59;
  const daysCount = 31;
  const startCol = 3; 
  
  let employees = [];
  for (let i = 1; i <= empCount; i++) employees.push([`Сотрудник ${i}`]);
  
  sheetReport.getRange("A1:A2").merge().setValue("ФИО Сотрудника").setVerticalAlignment("middle").setHorizontalAlignment("center").setFontWeight("bold");
  sheetReport.getRange("B1:B2").merge().setValue("ИТОГО").setVerticalAlignment("middle").setHorizontalAlignment("center").setFontWeight("bold");
  sheetReport.setColumnWidth(1, 180);
  sheetReport.setColumnWidth(2, 60);
  sheetReport.getRange(3, 1, employees.length, 1).setValues(employees);

  // === ГОТОВИМ МАССИВЫ ===
  let rowDates = new Array(daysCount * 3).fill("");     
  let rowHeaders = new Array(daysCount * 3).fill("");   
  let rowFormulas = new Array(daysCount * 3).fill("");  
  let rowFormats = new Array(daysCount * 3).fill("");   
  
  let year = 2025; 
  let month = 11; // Декабрь

  const getColLetter = (idx) => {
    let letter = "";
    while (idx >= 0) {
      letter = String.fromCharCode((idx % 26) + 65) + letter;
      idx = Math.floor(idx / 26) - 1;
    }
    return letter;
  };

  for (let day = 1; day <= daysCount; day++) {
    let blockIndex = (day - 1) * 3; 
    
    // 1. Дата
    let dateObj = new Date(year, month, day);
    rowDates[blockIndex] = dateObj; 
    
    // 2. Подзаголовки
    rowHeaders[blockIndex]   = "Часы";
    rowHeaders[blockIndex+1] = "Приход";
    rowHeaders[blockIndex+2] = "Уход";
    
    // 3. Формулы
    let colAbsIndex = startCol + blockIndex - 1;
    let colDateLet = getColLetter(colAbsIndex);
    let colHoursLet = getColLetter(colAbsIndex);
    let colInLet    = getColLetter(colAbsIndex+1); 
    let colOutLet   = getColLetter(colAbsIndex+2); 
    
    let dateAddr = `${colDateLet}$1`;
    
    let calcStart = `CEILING(${colInLet}3 - "00:10"; "1:00")`;
    let calcEnd   = `FLOOR(${colOutLet}3; "1:00")`;
    
    rowFormulas[blockIndex] = `=IF(OR(${colInLet}3=""; ${colOutLet}3=""); ""; (${calcEnd} - ${calcStart} + (${calcEnd} < ${calcStart})) * 24)`;
    rowFormulas[blockIndex+1] = `=IFERROR(MINIFS(DB_Logs!$B:$B; DB_Logs!$A:$A; ${dateAddr}; DB_Logs!$C:$C; $A3); "")`;
    rowFormulas[blockIndex+2] = `=IFERROR(MAXIFS(DB_Logs!$B:$B; DB_Logs!$A:$A; ${dateAddr}; DB_Logs!$C:$C; $A3); "")`;

    // 4. Форматы
    rowFormats[blockIndex]   = "0";     
    rowFormats[blockIndex+1] = "HH:mm"; 
    rowFormats[blockIndex+2] = "HH:mm"; 
  }

  // === ЗАПИСЬ ===
  let totalCols = daysCount * 3;
  
  sheetReport.getRange(1, 3, 1, totalCols).setValues([rowDates]).setNumberFormat("dd.MM (ddd)");
  sheetReport.getRange(2, 3, 1, totalCols).setValues([rowHeaders])
    .setFontSize(8).setHorizontalAlignment("center");
    
  let rangeRow3 = sheetReport.getRange(3, 3, 1, totalCols);
  rangeRow3.setFormulas([rowFormulas]);
  rangeRow3.setNumberFormats([rowFormats]);
  
  let destRange = sheetReport.getRange(4, 3, empCount - 1, totalCols);
  rangeRow3.copyTo(destRange);
  
  let totalRange = sheetReport.getRange(3, 2, empCount, 1);
  totalRange.setFormula(`=SUMIF($2:$2; "Часы"; 3:3)`);
  totalRange.setNumberFormat("0");

  SpreadsheetApp.flush(); 

  // === ОФОРМЛЕНИЕ (С ИЗМЕНЕННОЙ ШИРИНОЙ) ===
  sheetReport.setColumnWidths(3, totalCols, 60); // Базовая ширина
  
  for (let day = 1; day <= daysCount; day++) {
     let colIndex = startCol + (day - 1) * 3;
     
     sheetReport.getRange(1, colIndex, 1, 3).merge()
        .setHorizontalAlignment("center")
        .setBorder(true, true, true, true, null, null);
     
     // ИЗМЕНЕНИЕ ЗДЕСЬ:
     // "Часы" - 65 пикселей (чтобы влезла дата "01.12 (пн)")
     sheetReport.setColumnWidth(colIndex, 65); 
     
     // Приход и Уход - 60 пикселей (чуть свободнее)
     sheetReport.setColumnWidth(colIndex+1, 60);
     sheetReport.setColumnWidth(colIndex+2, 60);
  }

  sheetReport.setFrozenRows(2);
  sheetReport.setFrozenColumns(2);
  
  // === ЗЕБРА ===
  let bandingRange = sheetReport.getRange(3, 1, empCount, totalCols + 2);
  let banding = bandingRange.applyRowBanding(SpreadsheetApp.BandingTheme.LIGHT_GREY);
  banding.setHeaderRowColor(null);
  
  SpreadsheetApp.flush(); 

  // === ГРУППИРОВКА ===
  for (let day = 1; day <= daysCount; day++) {
    let colIndex = startCol + (day - 1) * 3; 
    try {
      sheetReport.getRange(1, colIndex + 1, sheetReport.getMaxRows(), 2).shiftColumnGroupDepth(1);
      if (day % 3 === 0) Utilities.sleep(300); 
    } catch (e) {
      Logger.log("Ошибка группировки: " + e.message);
    }
  }
  
  sheetReport.collapseAllColumnGroups();
  Logger.log("Готово (Столбцы расширены)!");
}