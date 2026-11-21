# Tira uma foto da tela inteira (usado no CI do Windows para ver a janela da Fornalha).
param([string]$Saida = "tela.png")
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
$bmp.Save($Saida, [System.Drawing.Imaging.ImageFormat]::Png)
Write-Host "foto salva em $Saida ($($b.Width)x$($b.Height))"
