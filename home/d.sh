def test_function() {
e=1
f=2
g=$((e + f))
echo $g
echo "hello"
echo "This is a test function."
}

echo "start func"
test_function()