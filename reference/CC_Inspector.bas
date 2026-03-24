' =============================================================================
' CC_Inspector - VBA Module for inspecting Content Controls and Custom XML
' =============================================================================
' Для использования:
' 1. В Word: Alt+F11 → Insert → Module → вставить этот код
' 2. Запуск: Alt+F8 → выбрать нужный макрос
'
' Макросы:
'   - InspectAll          : Полный отчёт (XML Data + все CC)
'   - InspectXMLData      : Только Custom XML Part (data storage)
'   - InspectContentControls : Только список CC с маппингом
'   - CheckSyncStatus     : Проверка синхронизации CC ↔ XML
' =============================================================================

Option Explicit

Private Const CUSTOM_XML_URI As String = "urn:draftbuilder:loan_agreement:v1"
Private Const STORE_ITEM_ID As String = "{12345678-1234-1234-1234-123456789ABC}"

' -----------------------------------------------------------------------------
' Главный макрос - полный отчёт
' -----------------------------------------------------------------------------
Public Sub InspectAll()
    Dim report As String
    report = "═══════════════════════════════════════════════════════════════" & vbCrLf
    report = report & "  ОТЧЁТ ПО CONTENT CONTROLS И CUSTOM XML" & vbCrLf
    report = report & "  Документ: " & ActiveDocument.Name & vbCrLf
    report = report & "  Дата: " & Format(Now, "dd.mm.yyyy hh:nn:ss") & vbCrLf
    report = report & "═══════════════════════════════════════════════════════════════" & vbCrLf & vbCrLf
    
    report = report & GetXMLDataReport() & vbCrLf
    report = report & GetContentControlsReport() & vbCrLf
    report = report & GetSyncStatusReport()
    
    ShowReport report, "CC Inspector - Полный отчёт"
End Sub

' -----------------------------------------------------------------------------
' Только Custom XML Data
' -----------------------------------------------------------------------------
Public Sub InspectXMLData()
    Dim report As String
    report = GetXMLDataReport()
    ShowReport report, "CC Inspector - Custom XML Data"
End Sub

' -----------------------------------------------------------------------------
' Только Content Controls
' -----------------------------------------------------------------------------
Public Sub InspectContentControls()
    Dim report As String
    report = GetContentControlsReport()
    ShowReport report, "CC Inspector - Content Controls"
End Sub

' -----------------------------------------------------------------------------
' Проверка синхронизации
' -----------------------------------------------------------------------------
Public Sub CheckSyncStatus()
    Dim report As String
    report = GetSyncStatusReport()
    ShowReport report, "CC Inspector - Синхронизация"
End Sub

' =============================================================================
' ВНУТРЕННИЕ ФУНКЦИИ
' =============================================================================

Private Function GetXMLDataReport() As String
    Dim s As String
    Dim xmlPart As CustomXMLPart
    Dim found As Boolean
    
    s = "┌─────────────────────────────────────────────────────────────┐" & vbCrLf
    s = s & "│  CUSTOM XML PART (Data Storage)                             │" & vbCrLf
    s = s & "└─────────────────────────────────────────────────────────────┘" & vbCrLf & vbCrLf
    
    found = False
    For Each xmlPart In ActiveDocument.CustomXMLParts
        If InStr(xmlPart.XML, CUSTOM_XML_URI) > 0 Then
            found = True
            s = s & "Namespace: " & CUSTOM_XML_URI & vbCrLf
            s = s & "Store ID:  " & STORE_ITEM_ID & vbCrLf & vbCrLf
            s = s & "Данные:" & vbCrLf
            s = s & "────────────────────────────────────────" & vbCrLf
            s = s & FormatXMLNodes(xmlPart.DocumentElement, 0)
            Exit For
        End If
    Next xmlPart
    
    If Not found Then
        s = s & "⚠ Custom XML Part не найден!" & vbCrLf
        s = s & "  Ожидаемый namespace: " & CUSTOM_XML_URI & vbCrLf
        s = s & vbCrLf & "Доступные CustomXMLParts:" & vbCrLf
        For Each xmlPart In ActiveDocument.CustomXMLParts
            s = s & "  - " & Left(xmlPart.XML, 100) & "..." & vbCrLf
        Next xmlPart
    End If
    
    GetXMLDataReport = s & vbCrLf
End Function

Private Function FormatXMLNodes(node As CustomXMLNode, level As Integer) As String
    Dim s As String
    Dim child As CustomXMLNode
    Dim indent As String
    Dim nodeValue As String
    
    indent = String(level * 2, " ")
    
    If node.NodeType = msoCustomXMLNodeElement Then
        nodeValue = Trim(node.Text)
        
        ' Проверяем, есть ли дочерние элементы
        Dim hasChildElements As Boolean
        hasChildElements = False
        For Each child In node.ChildNodes
            If child.NodeType = msoCustomXMLNodeElement Then
                hasChildElements = True
                Exit For
            End If
        Next child
        
        If hasChildElements Then
            s = indent & "📁 " & node.BaseName & vbCrLf
            For Each child In node.ChildNodes
                s = s & FormatXMLNodes(child, level + 1)
            Next child
        Else
            ' Листовой узел - показываем значение
            If Len(nodeValue) > 0 Then
                s = indent & "✓ " & node.BaseName & " = """ & TruncateText(nodeValue, 50) & """" & vbCrLf
            Else
                s = indent & "○ " & node.BaseName & " = (пусто)" & vbCrLf
            End If
        End If
    End If
    
    FormatXMLNodes = s
End Function

Private Function GetContentControlsReport() As String
    Dim s As String
    Dim cc As ContentControl
    Dim i As Integer
    Dim ccType As String
    Dim xpath As String
    Dim storeId As String
    
    s = "┌─────────────────────────────────────────────────────────────┐" & vbCrLf
    s = s & "│  CONTENT CONTROLS                                           │" & vbCrLf
    s = s & "└─────────────────────────────────────────────────────────────┘" & vbCrLf & vbCrLf
    
    s = s & "Всего CC в документе: " & ActiveDocument.ContentControls.Count & vbCrLf & vbCrLf
    
    i = 0
    For Each cc In ActiveDocument.ContentControls
        i = i + 1
        ccType = GetCCTypeName(cc.Type)
        
        s = s & "────────────────────────────────────────" & vbCrLf
        s = s & "#" & i & "  " & ccType & vbCrLf
        s = s & "    Title: " & IIf(Len(cc.Title) > 0, cc.Title, "(нет)") & vbCrLf
        s = s & "    Tag:   " & IIf(Len(cc.Tag) > 0, cc.Tag, "(нет)") & vbCrLf
        
        ' XML Mapping
        If cc.XMLMapping.IsMapped Then
            xpath = cc.XMLMapping.xpath
            storeId = ""
            On Error Resume Next
            storeId = cc.XMLMapping.CustomXMLPart.DocumentElement.NamespaceURI
            On Error GoTo 0
            
            s = s & "    XML Mapping: ✓ ПРИВЯЗАН" & vbCrLf
            s = s & "      XPath: " & xpath & vbCrLf
            s = s & "      NS:    " & storeId & vbCrLf
        Else
            s = s & "    XML Mapping: ✗ нет привязки" & vbCrLf
        End If
        
        ' Текущее значение
        s = s & "    Значение: """ & TruncateText(GetCCText(cc), 60) & """" & vbCrLf
    Next cc
    
    GetContentControlsReport = s & vbCrLf
End Function

Private Function GetSyncStatusReport() As String
    Dim s As String
    Dim cc As ContentControl
    Dim xmlPart As CustomXMLPart
    Dim xmlValue As String
    Dim ccValue As String
    Dim xpath As String
    Dim syncOK As Integer
    Dim syncFail As Integer
    Dim noMapping As Integer
    
    s = "┌─────────────────────────────────────────────────────────────┐" & vbCrLf
    s = s & "│  ПРОВЕРКА СИНХРОНИЗАЦИИ CC ↔ XML                            │" & vbCrLf
    s = s & "└─────────────────────────────────────────────────────────────┘" & vbCrLf & vbCrLf
    
    ' Найти наш Custom XML Part
    Set xmlPart = Nothing
    For Each xmlPart In ActiveDocument.CustomXMLParts
        If InStr(xmlPart.XML, CUSTOM_XML_URI) > 0 Then
            Exit For
        End If
    Next xmlPart
    
    If xmlPart Is Nothing Then
        s = s & "⚠ Custom XML Part не найден!" & vbCrLf
        GetSyncStatusReport = s
        Exit Function
    End If
    
    syncOK = 0
    syncFail = 0
    noMapping = 0
    
    For Each cc In ActiveDocument.ContentControls
        If cc.XMLMapping.IsMapped Then
            ccValue = GetCCText(cc)
            
            ' Получаем значение из XML
            On Error Resume Next
            xmlValue = ""
            xpath = cc.XMLMapping.xpath
            
            Dim xmlNode As CustomXMLNode
            Set xmlNode = xmlPart.SelectSingleNode(xpath)
            If Not xmlNode Is Nothing Then
                xmlValue = xmlNode.Text
            End If
            On Error GoTo 0
            
            ' Сравниваем
            If ccValue = xmlValue Then
                syncOK = syncOK + 1
            Else
                syncFail = syncFail + 1
                s = s & "⚠ РАССИНХРОН: " & cc.Tag & vbCrLf
                s = s & "   CC:  """ & TruncateText(ccValue, 40) & """" & vbCrLf
                s = s & "   XML: """ & TruncateText(xmlValue, 40) & """" & vbCrLf & vbCrLf
            End If
        Else
            noMapping = noMapping + 1
        End If
    Next cc
    
    s = s & "────────────────────────────────────────" & vbCrLf
    s = s & "ИТОГО:" & vbCrLf
    s = s & "  ✓ Синхронизировано: " & syncOK & vbCrLf
    s = s & "  ⚠ Рассинхронизировано: " & syncFail & vbCrLf
    s = s & "  ○ Без XML-маппинга: " & noMapping & vbCrLf
    
    GetSyncStatusReport = s & vbCrLf
End Function

' =============================================================================
' ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
' =============================================================================

Private Function GetCCTypeName(ccType As WdContentControlType) As String
    Select Case ccType
        Case wdContentControlRichText: GetCCTypeName = "[RichText]"
        Case wdContentControlText: GetCCTypeName = "[PlainText]"
        Case wdContentControlDate: GetCCTypeName = "[Date]"
        Case wdContentControlDropdownList: GetCCTypeName = "[Dropdown]"
        Case wdContentControlComboBox: GetCCTypeName = "[ComboBox]"
        Case wdContentControlCheckBox: GetCCTypeName = "[CheckBox]"
        Case wdContentControlRepeatingSection: GetCCTypeName = "[Repeating]"
        Case Else: GetCCTypeName = "[Type:" & ccType & "]"
    End Select
End Function

Private Function GetCCText(cc As ContentControl) As String
    On Error Resume Next
    If cc.Type = wdContentControlDate Then
        GetCCText = cc.Range.Text
    Else
        GetCCText = cc.Range.Text
    End If
    On Error GoTo 0
End Function

Private Function TruncateText(txt As String, maxLen As Integer) As String
    txt = Replace(txt, vbCr, " ")
    txt = Replace(txt, vbLf, " ")
    txt = Replace(txt, vbTab, " ")
    
    If Len(txt) > maxLen Then
        TruncateText = Left(txt, maxLen - 3) & "..."
    Else
        TruncateText = txt
    End If
End Function

Private Sub ShowReport(report As String, title As String)
    ' Создаём новый документ с отчётом
    Dim doc As Document
    Set doc = Documents.Add
    
    doc.Content.Font.Name = "Consolas"
    doc.Content.Font.Size = 10
    doc.Content.Text = report
    
    ' Заголовок окна
    doc.ActiveWindow.Caption = title
    
    MsgBox "Отчёт создан в новом документе." & vbCrLf & vbCrLf & _
           "Tip: Design Mode должен быть ВЫКЛЮЧЕН для корректной синхронизации CC с XML.", _
           vbInformation, title
End Sub
