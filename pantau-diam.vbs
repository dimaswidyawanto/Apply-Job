' Menjalankan pantau.bat tanpa jendela (dipakai oleh pasang-otomatis.bat).
' Semua keluaran dicatat ke pantau.log di folder program.
Dim fso, sh, folder, log
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

folder = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = folder

log = """" & folder & "\pantau.log" & """"
sh.Run "cmd /c pantau.bat 60 >> " & log & " 2>&1", 0, False
