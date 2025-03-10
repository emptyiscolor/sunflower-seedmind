#!/bin/bash

# Usage: ./send_single_task.sh {libpng|libexif|libxml2|jedis}
if [ "$#" -ne 1 ]; then
  echo "Usage: $0 {libpng|libexif|libxml2|jedis}"
  exit 1
fi

case "$1" in
    libpng)
        payload='{"focus":"example-libpng","diff":"/workspaces/sunflower/local_test_aixcc/libpng/libpng_diff.tar.gz","fuzzing_tooling":"/workspaces/sunflower/local_test_aixcc/libpng/libpng_tooling.tar.gz","project_name":"libpng","repo":["/workspaces/sunflower/local_test_aixcc/libpng/libpng_src.tar.gz"],"task_id":"51f81839-7dab-4295-b05b-d67ecdbe35c7","task_type":"delta"}'
        ;;
    libexif)
        payload='{"focus":"libexif","diff":"/workspaces/sunflower/local_test_aixcc/libexif/libexif_diff.tar.gz","fuzzing_tooling":"/workspaces/sunflower/local_test_aixcc/libexif/libexif_tooling.tar.gz","project_name":"libexif","repo":["/workspaces/sunflower/local_test_aixcc/libexif/libexif_src.tar.gz"],"task_id":"fd99adfd-069a-4359-98dc-0dd702045ff4","task_type":"delta"}'
        ;;
    libxml2)
        payload='{"focus":"libxml2","diff":"/workspaces/sunflower/local_test_aixcc/libxml2/libxml2_diff.tar.gz","fuzzing_tooling":"/workspaces/sunflower/local_test_aixcc/libxml2/libxml2_tooling.tar.gz","project_name":"libxml2","repo":["/workspaces/sunflower/local_test_aixcc/libxml2/libxml2_src.tar.gz"],"task_id":"67c5a094-eaa7-440c-ad46-e07ee206a398","task_type":"delta"}'
        ;;
    jedis)
        payload='{"focus":"buggy-exemplar-challenge-jvm-jedis","fuzzing_tooling":"/workspaces/sunflower/local_test_aixcc/jedis/jedis_tooling.tar.gz","project_name":"jedis","repo":["/workspaces/sunflower/local_test_aixcc/jedis/jedis_src.tar.gz"],"task_id":"f6dfe86d-0edd-4de5-98f2-b315bd723a0b","task_type":"full"}'
        ;;
    *)
        echo "Usage: $0 {libpng|libexif|libxml2|jedis}"
        exit 1
        ;;
esac

./rabbitmqadmin --host=localhost --port=15672 --username=guest --password=guest publish exchange=amq.default routing_key=seedgen_queue payload="${payload}"