' Menjalankan pantau.bat tanpa jendela (dipakai oleh pasang-otomatis.bat).
' Semua keluaran dicatat ke pantau.log di folder program.
Dim fso, sh, folder, berkasLog, cmdPath, jalur, log
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

folder = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = folder
cmdPath = sh.ExpandEnvironmentStrings("%COMSPEC%")
berkasLog = folder & "\pantau.log"
log = """" & berkasLog & """"
jalur = """" & cmdPath & """ /d /c ""pantau.bat 60 >> " & log & " 2>&1"""

' Catat saat pemantau dinyalakan supaya mudah diperiksa di pantau.log.
Dim tulis
Set tulis = fso.OpenTextFile(berkasLog, 8, True)
tulis.WriteLine "[" & Now & "] pemantau dinyalakan (" & WScript.ScriptName & ")"
tulis.WriteLine "[" & Now & "] perintah: " & jalur
tulis.Close

sh.Run jalur, 0, False
