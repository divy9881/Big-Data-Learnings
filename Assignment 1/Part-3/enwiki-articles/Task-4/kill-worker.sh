sudo sh -c "sync; echo 3 > /proc/sys/vm/drop_caches"
kill -9 $1