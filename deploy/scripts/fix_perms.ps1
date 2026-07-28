$path = "C:\Makemystay\makemystay-backend.pem"
if (Test-Path $path) {
    Write-Host "Found file: $path"
    try {
        $acl = Get-Acl $path
        # Disable inheritance and remove existing rules ($false)
        $acl.SetAccessRuleProtection($true, $false)
        
        # Create rule for current user
        $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($currentUser, "FullControl", "Allow")
        
        # Add the rule
        $acl.SetAccessRule($rule)
        
        # Apply the ACL
        Set-Acl $path $acl
        Write-Host "Permissions successfully updated for $currentUser"
        
        # Verification
        $newAcl = Get-Acl $path
        $newAcl.Access | Format-Table IdentityReference,FileSystemRights,AccessControlType -AutoSize
    } catch {
        Write-Error "Error updating permissions: $_"
    }
} else {
    Write-Host "File NOT found at: $path"
    Write-Host "Listing directory C:\Makemystay:"
    Get-ChildItem "C:\Makemystay" | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize
}
