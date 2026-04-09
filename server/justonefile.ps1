# Read all the py files recursively in the engine directory and gives back a single py file as concatenation of all the files. This is used to create a single file version of the engine for easier deployment and debugging.
$engine_dir = "engine"
$output_file = "justonefile.py"

# Get all the py files in the engine directory and its subdirectories
$py_files = Get-ChildItem -Path $engine_dir -Recurse -Filter *.py
# Concatenate the contents of all the py files into a single string
$all_code = ""
foreach ($file in $py_files) {
    $code = Get-Content -Path $file.FullName -Raw
    $all_code += "`n`n# File: " + $file.FullName + "`n" + $code
}
# Write the concatenated code to the output file
Set-Content -Path $output_file -Value $all_code