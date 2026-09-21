# 图片素材出处

本目录下的城市照片来自 Wikimedia Commons，均为自由授权作品，**按各自协议要求署名**。
抓取脚本：`infra/scripts/fetch_assets.py`（本项目为离线教学演示，一次抓取后本地使用）。
底图 `map/china.svg` 来自 Wikimedia Commons 的定位地图系列，授权 CC BY-SA 3.0。

> 换图或商用前，请回到来源页确认最新授权条款，并保留同样的署名。

| 城市 | 文件 | 作者 | 授权 | 来源页 |
| :--- | :--- | :--- | :--- | :--- |
| PEK | `cities/PEK.jpg` | Lloyd Tudor | CC BY-SA 4.0 | [File:Temple of Heaven, Beijing - February 2024.jpg](https://commons.wikimedia.org/wiki/File:Temple_of_Heaven,_Beijing_-_February_2024.jpg) |
| CTU | `cities/CTU.jpg` | George Lu | CC BY 2.0 | [File:Panda in Chengdu Research Base of Giant Panda Breeding - 7708872342.jpg](https://commons.wikimedia.org/wiki/File:Panda_in_Chengdu_Research_Base_of_Giant_Panda_Breeding_-_7708872342.jpg) |
| SHA | `cities/SHA.jpg` | King of Hearts | CC BY-SA 4.0 | [File:Pudong Shanghai November 2017 panorama.jpg](https://commons.wikimedia.org/wiki/File:Pudong_Shanghai_November_2017_panorama.jpg) |
| SYX | `cities/SYX.jpg` | Dounai | CC BY-SA 3.0 | [File:Abandoned hotel Sanya Hainan 1999.jpg](https://commons.wikimedia.org/wiki/File:Abandoned_hotel_Sanya_Hainan_1999.jpg) |
| XIY | `cities/XIY.jpg` | Ideophagous | CC BY-SA 4.0 | [File:Xi'an city walls.jpg](https://commons.wikimedia.org/wiki/File:Xi%27an_city_walls.jpg) |
| HGH | `cities/HGH.jpg` | Y Chen | CC BY-SA 4.0 | [File:Hangzhou Skyline against the West Lake.png](https://commons.wikimedia.org/wiki/File:Hangzhou_Skyline_against_the_West_Lake.png) |
| CAN | `cities/CAN.jpg` | Daniel Lu (User:dllu) | CC BY-SA 4.0 | [File:Canton Tower at night Guangzhou 2024 dllu.jpg](https://commons.wikimedia.org/wiki/File:Canton_Tower_at_night_Guangzhou_2024_dllu.jpg) |
| SZX | `cities/SZX.jpg` | Dinkun Chen | CC BY-SA 4.0 | [File:TOP OF THE DIWANG BUILDING SEE SHENZHEN SKYLINE (19).jpg](https://commons.wikimedia.org/wiki/File:TOP_OF_THE_DIWANG_BUILDING_SEE_SHENZHEN_SKYLINE_(19).jpg) |
| KMG | `cities/KMG.jpg` | CEphoto, Uwe Aranas | CC BY-SA 3.0 | [File:Shilin Yunnan China Shilin-Stone-Forest-11.jpg](https://commons.wikimedia.org/wiki/File:Shilin_Yunnan_China_Shilin-Stone-Forest-11.jpg) |
| CKG | `cities/CKG.jpg` | HoweyYuan | CC BY-SA 4.0 | [File:Hongya Cave 20240722.jpg](https://commons.wikimedia.org/wiki/File:Hongya_Cave_20240722.jpg) |
| XMN | `cities/XMN.jpg` | Slyronit | CC BY-SA 4.0 | [File:Gulangyu Island from Zhongshan Road, Xiamen.jpg](https://commons.wikimedia.org/wiki/File:Gulangyu_Island_from_Zhongshan_Road,_Xiamen.jpg) |
| WUH | `cities/WUH.jpg` | Gary Todd from Xinzheng, China | CC0 | [File:Wuhan, Viewed from Yellow Crane Tower 3 (G. Todd) - Flickr.jpg](https://commons.wikimedia.org/wiki/File:Wuhan,_Viewed_from_Yellow_Crane_Tower_3_(G._Todd)_-_Flickr.jpg) |
| LXA | `cities/LXA.jpg` | cattan2011 | CC BY 2.0 | [File:The city - Potala Palace - Lhasa, Tibet.jpg](https://commons.wikimedia.org/wiki/File:The_city_-_Potala_Palace_-_Lhasa,_Tibet.jpg) |
| LJG | `cities/LJG.jpg` | CEphoto, Uwe Aranas | CC BY-SA 3.0 | [File:Lijiang Yunnan China Jade-Dragon-Snow-Mountain-01.jpg](https://commons.wikimedia.org/wiki/File:Lijiang_Yunnan_China_Jade-Dragon-Snow-Mountain-01.jpg) |
| TAO | `cities/TAO.jpg` | Benlisquare | CC BY-SA 4.0 | [File:Evening lightshow at Zhanqiao Pier.jpg](https://commons.wikimedia.org/wiki/File:Evening_lightshow_at_Zhanqiao_Pier.jpg) |
| HRB | `cities/HRB.jpg` | 闫恩铭 / Enming Yan | CC BY-SA 4.0 | [File:Saint Sophia Cathedral, Harbin 10.jpg](https://commons.wikimedia.org/wiki/File:Saint_Sophia_Cathedral,_Harbin_10.jpg) |

## 底图

`map/china.svg` 来自 Wikimedia Commons 的定位地图系列：[File:China edcp location map.svg](https://commons.wikimedia.org/wiki/File:China_edcp_location_map.svg)，作者 Uwe Dedering，授权 **CC BY-SA 3.0**。 底图是等距圆柱投影，边界为东经 72–136、北纬 17–54，站点坐标按这个边界线性换算（见 `web/present/art.py` 的 `map_xy`）。

界面上地图下方会显示一行署名——这是 CC 授权的要求，不是装饰。
