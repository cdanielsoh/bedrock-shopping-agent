export interface User {
  id: string;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  addresses: string;
  age: number;
  gender: string;
  persona: string;
  discount_persona: string;
}

export const users: User[] = [
  {
    id: "15",
    username: "user15",
    email: "minsu.kim@example.com",
    first_name: "민수",
    last_name: "김",
    addresses: "{'address':'서울시 강남구 테헤란로 152길 신사동 301호', 'zipcode':'06294'}",
    age: 28,
    gender: "M",
    persona: "seasonal_furniture_floral",
    discount_persona: "lower_priced_products"
  },
  {
    id: "314",
    username: "user314",
    email: "junho.lee@example.com",
    first_name: "준호",
    last_name: "이",
    addresses: "{'address':'서울시 종로구 세종대로 89길 청운동 205호', 'zipcode':'03032'}",
    age: 31,
    gender: "M",
    persona: "books_apparel_homedecor",
    discount_persona: "lower_priced_products"
  },
  {
    id: "683",
    username: "user683",
    email: "seongwoo.park@example.com",
    first_name: "성우",
    last_name: "박",
    addresses: "{'address':'서울시 마포구 홍익로 76길 합정동 402호', 'zipcode':'04039'}",
    age: 25,
    gender: "M",
    persona: "seasonal_furniture_floral",
    discount_persona: "all_discounts"
  },
  {
    id: "751",
    username: "user751",
    email: "daehyeon.choi@example.com",
    first_name: "대현",
    last_name: "최",
    addresses: "{'address':'서울시 송파구 올림픽로 234길 잠실동 105호', 'zipcode':'05508'}",
    age: 33,
    gender: "M",
    persona: "books_apparel_homedecor",
    discount_persona: "all_discounts"
  },
  {
    id: "804",
    username: "user804",
    email: "jaemin.jung@example.com",
    first_name: "재민",
    last_name: "정",
    addresses: "{'address':'서울시 서초구 반포대로 167길 반포동 602호', 'zipcode':'06591'}",
    age: 29,
    gender: "M",
    persona: "apparel_footwear_accessories",
    discount_persona: "lower_priced_products"
  },
  {
    id: "836",
    username: "user836",
    email: "taeyeong.kang@example.com",
    first_name: "태영",
    last_name: "강",
    addresses: "{'address':'서울시 용산구 이태원로 45길 이태원동 203호', 'zipcode':'04348'}",
    age: 27,
    gender: "M",
    persona: "homedecor_electronics_outdoors",
    discount_persona: "all_discounts"
  },
  {
    id: "1373",
    username: "user1373",
    email: "sanghyeon.yoon@example.com",
    first_name: "상현",
    last_name: "윤",
    addresses: "{'address':'서울시 영등포구 여의대로 123길 여의도동 701호', 'zipcode':'07327'}",
    age: 35,
    gender: "M",
    persona: "groceries_seasonal_tools",
    discount_persona: "discount_indifferent"
  },
  {
    id: "1403",
    username: "user1403",
    email: "donghoon.lim@example.com",
    first_name: "동훈",
    last_name: "임",
    addresses: "{'address':'서울시 성동구 왕십리로 87길 성수동 304호', 'zipcode':'04780'}",
    age: 30,
    gender: "M",
    persona: "footwear_jewelry_furniture",
    discount_persona: "all_discounts"
  },
  {
    id: "1494",
    username: "user1494",
    email: "jiho.han@example.com",
    first_name: "지호",
    last_name: "한",
    addresses: "{'address':'서울시 광진구 아차산로 198길 구의동 506호', 'zipcode':'05014'}",
    age: 26,
    gender: "M",
    persona: "accessories_groceries_books",
    discount_persona: "discount_indifferent"
  }
];

export const getUserById = (id: string): User | undefined => {
  return users.find(user => user.id === id);
};

export const getUserDisplayName = (user: User): string => {
  return `${user.last_name}${user.first_name} (${user.username})`;
};
