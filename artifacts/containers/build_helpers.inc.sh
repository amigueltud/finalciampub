OPSYS=`uname`

f_BUILD=ciam_build.txt
f_SESSIONS=ciam_sessions.txt

export SCONE_CAS_ADDR="cas"
export CAS_MRENCLAVE="abcde0123456789abcde0123456789abcde0123456789abcde0123456789abcd"

function get_value {
	test 1 -eq `grep -c "^${1}=" ${2}` && test -n "$(grep "^${1}=" ${2} |tail -1 |cut -d '=' -f 2)" && grep "^${1}=" ${2} |tail -1 |cut -d '=' -f 2 || (echo "..:ERR: $2 has no unique value for $1" >/dev/stderr; false)
}

