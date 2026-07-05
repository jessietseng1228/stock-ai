const { createClient } = require('@supabase/supabase-js')

// 讀 Render 環境變數
const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_ROLE_KEY
)

async function test() {
  const { data, error } = await supabase
    .from('user_stocks')
    .select('*')
    .limit(1)

  console.log('===== SUPABASE TEST =====')
  console.log('data:', data)
  console.log('error:', error)
}

test()