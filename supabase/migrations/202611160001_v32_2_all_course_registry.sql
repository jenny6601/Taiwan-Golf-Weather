-- V32.2: Register all 57 Taiwan golf courses for live observation station mapping.
-- Preserve separate rolling rainfall windows from CWA O-A0002-001.
alter table public.observation_hourly
  add column if not exists precipitation_10m_mm double precision,
  add column if not exists precipitation_1h_mm double precision;

-- Run after 202611130001_v32_1_observations.sql.
insert into public.courses (id,name,county,address,latitude,longitude,timezone,active)
values
('TWG001','臺灣高爾夫俱樂部球場（老淡水）','新北市','新北市淡水區油車里中正路一段6巷32號',25.1747,121.4389,'Asia/Taipei',true),
('TWG002','揮皇','新北市','新北市淡水區八勢里八勢路300號',25.1581,121.4553,'Asia/Taipei',true),
('TWG003','大屯','新北市','新北市淡水區坤山里商工路309號',25.1633,121.4647,'Asia/Taipei',true),
('TWG004','北投國華','新北市','新北市淡水區坪頂里小坪頂23之1號',25.1486,121.5031,'Asia/Taipei',true),
('TWG005','八里國際','新北市','新北市林口區嘉寶里寶斗厝坑91號',25.1328,121.365,'Asia/Taipei',true),
('TWG006','美麗華','新北市','新北市林口區下福里下福路9號',25.0758,121.3411,'Asia/Taipei',true),
('TWG007','林口','新北市','新北市林口區湖北里後湖50之1號',25.0714,121.3719,'Asia/Taipei',true),
('TWG008','幸福','新北市','新北市林口區下福里71之1號',25.0833,121.3361,'Asia/Taipei',true),
('TWG009','東華','新北市','新北市林口區下福里7鄰93-1號',25.0806,121.3314,'Asia/Taipei',true),
('TWG010','黃金海岸（北海）','新北市','新北市石門區草里里草埔尾5號',25.2711,121.5722,'Asia/Taipei',true),
('TWG011','濱海','新北市','新北市石門區尖鹿里尖仔路10號',25.2861,121.5583,'Asia/Taipei',true),
('TWG012','翡翠','新北市','新北市萬里區北基里仁七街16-1號',25.1786,121.6819,'Asia/Taipei',true),
('TWG013','台北','桃園市','桃園市蘆竹區坑子里赤塗崎34之1號',25.0489,121.2825,'Asia/Taipei',true),
('TWG014','統帥','桃園市','桃園市蘆竹區營盤里六福一路195巷1弄8號',25.0417,121.2958,'Asia/Taipei',true),
('TWG015','第一','桃園市','桃園市蘆竹區坑子村7鄰貓尾崎50號',25.0611,121.2836,'Asia/Taipei',true),
('TWG016','永漢','桃園市','桃園市蘆竹區山腳里9鄰南山北路一段300號',25.0592,121.2917,'Asia/Taipei',true),
('TWG017','長庚','桃園市','桃園市龜山區舊路里長庚球場路66號',25.0336,121.3694,'Asia/Taipei',true),
('TWG018','東方','桃園市','桃園市龜山區舊路里東方球場路100號',25.0381,121.3614,'Asia/Taipei',true),
('TWG019','楊梅','桃園市','桃園市楊梅區東流里13鄰崩坡73號',24.9125,121.1833,'Asia/Taipei',true),
('TWG020','揚昇','桃園市','桃園市楊梅區楊昇路256號',24.9208,121.1878,'Asia/Taipei',true),
('TWG021','桃園','桃園市','桃園市龍潭區九龍里29鄰悅華路100號',24.8789,121.2069,'Asia/Taipei',true),
('TWG022','龍潭','桃園市','桃園市龍潭區三林里民生路439巷130號',24.8569,121.2183,'Asia/Taipei',true),
('TWG023','大溪','桃園市','桃園市大溪區永福里日新路168號',24.8472,121.2811,'Asia/Taipei',true),
('TWG024','新豐（新竹）','新竹縣','新竹縣新豐鄉上坑村坑子口104號',24.8833,121.0361,'Asia/Taipei',true),
('TWG025','再興','新竹縣','新竹縣湖口鄉長安村再興路350號',24.8528,121.0306,'Asia/Taipei',true),
('TWG026','山溪地','新竹縣','新竹縣關西鎮玉山里2鄰13號',24.7861,121.1736,'Asia/Taipei',true),
('TWG027','立益','新竹縣','新竹縣關西鎮湖肚段55號',24.7917,121.1778,'Asia/Taipei',true),
('TWG028','老爺關西','新竹縣','新竹縣關西鎮玉山里1鄰赤柯山1號',24.7944,121.1708,'Asia/Taipei',true),
('TWG029','旭陽','新竹縣','新竹縣關西鎮南新里新城段100號',24.7972,121.1611,'Asia/Taipei',true),
('TWG030','寶山','新竹縣','新竹縣寶山鄉新城村寶新路二段465號',24.7556,121.0278,'Asia/Taipei',true),
('TWG031','皇家','苗栗縣','苗栗縣頭屋鄉明德村1鄰明德路6之11號',24.5889,120.9306,'Asia/Taipei',true),
('TWG032','全國花園','苗栗縣','苗栗縣苑裡鎮石鎮里1鄰1之1號',24.4444,120.6583,'Asia/Taipei',true),
('TWG033','台中國際','台中市','臺中市北屯區民政里北坑巷21-8號',24.1972,120.7611,'Asia/Taipei',true),
('TWG034','豐原','台中市','臺中市豐原區南嵩里水源路坪頂巷23號',24.2528,120.7306,'Asia/Taipei',true),
('TWG035','空軍清泉崗','台中市','臺中市清水區楊厝里和睦路二段305號',24.2694,120.575,'Asia/Taipei',true),
('TWG036','霧峰','台中市','臺中市霧峰區峰谷里峰谷路668號',24.0389,120.6972,'Asia/Taipei',true),
('TWG037','彰化','彰化縣','彰化縣彰化市延和里大埔路2巷101號',24.0694,120.5417,'Asia/Taipei',true),
('TWG038','台豐','彰化縣','彰化縣大村鄉福興村學府路77號',23.9722,120.5583,'Asia/Taipei',true),
('TWG039','南峰','南投縣','南投縣南投市鳳山路336-1號',23.8611,120.6861,'Asia/Taipei',true),
('TWG040','松柏嶺','南投縣','南投縣名間鄉炭寮村頂頂巷36之1號',23.8333,120.7139,'Asia/Taipei',true),
('TWG041','棕梠湖','嘉義縣','嘉義縣番路鄉新福村第三農場24號',23.4111,120.6278,'Asia/Taipei',true),
('TWG042','斑芝花','台南市','臺南市東山區東原里斑芝花坑39號',23.2389,120.5139,'Asia/Taipei',true),
('TWG043','嘉南','台南市','臺南市官田區社子里六雙21號',23.1972,120.3583,'Asia/Taipei',true),
('TWG044','台南（新化）','台南市','臺南市新化區礁坑里100號',23.0333,120.3306,'Asia/Taipei',true),
('TWG045','南寶','台南市','臺南市大內區頭社里136號',23.2056,120.4472,'Asia/Taipei',true),
('TWG046','南一','台南市','臺南市關廟區布袋里長榮街500號',22.9556,120.3556,'Asia/Taipei',true),
('TWG047','觀音山','高雄市','高雄市大樹區三和里三和路140號',22.7556,120.3889,'Asia/Taipei',true),
('TWG048','信誼','高雄市','高雄市大樹區統嶺里信誼路1號',22.7639,120.4833,'Asia/Taipei',true),
('TWG049','大崗山','高雄市','高雄市田寮區西德里長山路1號',22.8861,120.3306,'Asia/Taipei',true),
('TWG050','山湖觀','屏東縣','屏東縣高樹鄉廣興村中正路190號',22.8611,120.5833,'Asia/Taipei',true),
('JIAOXI','礁溪','宜蘭縣','宜蘭縣礁溪鄉林美村林尾路156號',24.8389,121.7389,'Asia/Taipei',true),
('TWG052','花蓮','花蓮縣','花蓮縣花蓮市化道路120號',23.9889,121.6056,'Asia/Taipei',true),
('TWG053','鴻禧太平','台中市','臺中市太平區頭汴里北田路265巷9號',24.15,120.7722,'Asia/Taipei',true),
('TWG054','中興新村','南投縣','南投縣南投市中興新村光明一路351號',23.9556,120.6861,'Asia/Taipei',true),
('TWG055','嘉光','嘉義縣','嘉義縣水上鄉南鄉村鹿寮12號',23.45,120.4167,'Asia/Taipei',true),
('TWG056','左營海軍','高雄市','高雄市左營區長壽路1號',22.6889,120.2889,'Asia/Taipei',true),
('TWG057','大衛營','高雄市','高雄市旗山區大林里溝坪路98-3號',22.8667,120.5056,'Asia/Taipei',true)
on conflict (id) do update set
 name=excluded.name, county=excluded.county, address=excluded.address,
 latitude=excluded.latitude, longitude=excluded.longitude,
 timezone=excluded.timezone, active=excluded.active, updated_at=now();

create index if not exists idx_courses_active_location on public.courses(active,latitude,longitude);
create index if not exists idx_station_course_map_nearest on public.station_course_map(course_id,distance_km)
 where representativeness <> 'rejected';
create index if not exists idx_observation_latest_quality on public.observation_hourly(station_id,dataset_code,observed_at desc)
 where quality_status in ('passed','pending');
