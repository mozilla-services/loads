How to debug loads
##################

Sometimes, on heavy load, Loads doesn't behaves the way you want it to. That's
really unfortunate, and we are working hard for this not to happen, but
sometimes things screw up ;).

I have a run stallen on my Loads cluster, how do I remove it?
=============================================================

You should have a run-id. If you remove the key from redis on the broker, you
should be all set::

    you@yourserver:~$ redis-cli                                     
    redis 127.0.0.1:6379> SMEMBERS runs                                    
     1) "91a776e9-c683-4fc8-bc07-5d4977f01ee0"                             
     2) "8a9a1ca2-69ac-4a97-9ccb-d8c464e45c61"                             
     3) "eef0a825-2fb3-4d32-8182-57f3c7ae28d9"                             
     4) "ece0d0fa-2459-4716-b22d-f86299d61d8b"                             
     5) "3335950b-604c-438d-8afe-5097d7ba9e17"                             
     6) "2f0f0e98-5446-44fc-9368-26e9e13696cb"                             
     7) "1f04a769-527d-4588-88af-e9c04f6edd63"                             
     8) "9112a522-1132-4856-809e-6d0ae538b9b5"                             
     9) "ece020de-7009-4333-8b5c-e003b10d412b"                             
    10) "9949cd41-b70d-4d7a-bf94-d5d618f433a7"                             
    11) "6e559e29-ff43-4b6d-8ef7-6b768ba763bd"                             
    12) "e1e1222a-be09-4519-a31b-4730e0509659"                             
    redis 127.0.0.1:6379> SREM runs e1e1222a-be09-4519-a31b-4730e0509659
