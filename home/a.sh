#!/bin/bash

a=5
b=3
c=$((a + b))
echo $c
c=$((c+1))
echo $c

if [ $c -gt 7 ];
echo "c is greater than 7"
else
echo "c is less than or equal to 7"
fi

while [ $c -lt 12 ];
echo $c
c=$((c+1))
done

while [ $c -lt 15 ];
c=$((c+1))
echo $c
done

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

def test_function_two(param1,param2) {
local a=$param1
local b=$param2
local result=$((a+b))
return $result
}

d=$(test_function_two(1,3))
echo "return : $d"
